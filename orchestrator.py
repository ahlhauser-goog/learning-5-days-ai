# ==============================================================================
# AGENT ORCHESTRATOR MODULE (orchestrator.py)
# ==============================================================================
# This module is the "brain" of our program. It orchestrates the two agents,
# handles history compaction, saves/restores conversation state (session persistence),
# and implements the main interactive command-line loop.
#
# Because calling AI models over the network takes time, we use Python's "asyncio" 
# (Asynchronous Input/Output) library, allowing the program to wait for network 
# responses without blocking the entire program.

import os
import json
import asyncio
from google import genai
from google.genai import types

# Import our helper modules
import state
from logger import StructuredLogger
from agents import LINTER_SYSTEM_INSTRUCTION, TEACHER_SYSTEM_INSTRUCTION, MODEL_ROUTING
import tools

# Initialize structured logging
logger = StructuredLogger()

class AgentOrchestrator:
    # Constructor function that sets up our orchestrator.
    # 'client: genai.Client' is the Google GenAI SDK client object.
    def __init__(self, file_path: str, client: genai.Client, session_file: str = "session_state.json"):
        # os.path.abspath resolves relative paths (like './script.sh') into absolute paths
        self.file_path = os.path.abspath(file_path)
        self.client = client
        self.session_file = session_file
        # This will hold the active Chat session object with the Refactor Teacher
        self.teacher_chat = None

    # 'async def' defines an asynchronous function (coroutine). 
    # To run this function, we must use the 'await' keyword.
    async def save_session(self):
        """Saves current state and chat history to session_file."""
        if not state.state:
            return
        
        try:
            history_data = []
            if self.teacher_chat:
                # Retrieve the full list of message objects in the teacher's history
                history = self.teacher_chat.get_history()
                # We call '.model_dump()' on each Content model. 
                # This converts the complex Pydantic objects into simple Python dictionaries.
                history_data = [c.model_dump() for c in history]

            # Construct a dictionary containing all session data
            session_data = {
                "file_path": state.state.file_path,
                "content": state.state.content,
                "original_content": state.state.original_content,
                "issues_list": state.state.issues_list,
                "current_step": state.state.current_step,
                "completed": state.state.completed,
                "teacher_history": history_data
            }
            
            # Open the session file in write mode ('w') and save the JSON
            # indent=2 formats the text nicely with indentations so humans can read it
            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)
            logger.log_session_save(self.session_file, True)
        except Exception as e:
            # If saving fails, log the failure and warn the user
            logger.log_session_save(self.session_file, False, str(e))
            print(f"\033[1;31mWarning: Failed to save session: {str(e)}\033[0m")

    async def load_session(self) -> bool:
        """Loads state and history from session_file if it exists."""
        if not os.path.exists(self.session_file):
            return False
            
        try:
            # Open the session file in read mode ('r')
            with open(self.session_file, "r") as f:
                data = json.load(f)
                
            # Verify that the saved session file matches the file we are currently refactoring
            if os.path.abspath(data["file_path"]) != self.file_path:
                return False
                
            # Restore the ScriptState object with loaded data
            state.state = state.ScriptState(data["file_path"], data["content"])
            state.state.original_content = data["original_content"]
            state.state.issues_list = data["issues_list"]
            state.state.current_step = data["current_step"]
            state.state.completed = data["completed"]
            
            # Reconstruct teacher history list
            loaded_history = []
            for item in data.get("teacher_history", []):
                # model_validate converts the simple dictionaries back into formal Pydantic Content models
                loaded_history.append(types.Content.model_validate(item))
                
            # Re-initialize the Refactor Teacher chat with all tools and system instructions
            config = types.GenerateContentConfig(
                tools=[
                    tools.get_script_content,
                    tools.propose_refactor,
                    tools.run_shellcheck,
                    tools.verify_script,
                    tools.save_changes,
                ],
                system_instruction=TEACHER_SYSTEM_INSTRUCTION,
                temperature=0.0
            )
            
            # Re-create the chat session, passing the restored history.
            # This allows the model to remember what was discussed in the last session!
            self.teacher_chat = self.client.chats.create(
                model=MODEL_ROUTING["teacher"],
                config=config,
                history=loaded_history
            )
            
            logger.log_session_load(self.session_file, True)
            return True
        except Exception as e:
            logger.log_session_load(self.session_file, False, str(e))
            print(f"\033[1;31mWarning: Failed to load session: {str(e)}\033[0m")
            return False

    async def compact_history_if_needed(self):
        """Compacts teacher chat history if it grows too large to save context tokens."""
        if not self.teacher_chat:
            return
            
        history = self.teacher_chat.get_history()
        # Compact history only if it contains 12 or more message entries (6 turns)
        if len(history) < 12:
            return
            
        logger.log_compaction(len(history), 0)
        print("\033[1;34m[System: Compacting chat history to save context space...]\033[0m")
        
        # We split the history into two lists:
        # - to_summarize: everything except the last 4 messages.
        # - keep: the last 4 messages (which we want to keep intact so the model remembers the active topic).
        # history[:-4] is a slice representing all items from start up to index -4 (4th from the end).
        # history[-4:] represents all items from the 4th item from the end to the very end.
        to_summarize = history[:-4]
        keep = history[-4:]
        
        # Build a text transcript representing the conversation we want to compact
        transcript = ""
        for msg in to_summarize:
            role = msg.role # 'user' or 'model'
            parts_text = []
            for part in msg.parts:
                if part.text:
                    parts_text.append(part.text)
                elif part.function_call:
                    parts_text.append(f"calls tool '{part.function_call.name}' with args {part.function_call.args}")
                elif part.function_response:
                    parts_text.append(f"tool response '{part.function_response.name}': {part.function_response.response}")
            transcript += f"{role.capitalize()}: {' | '.join(parts_text)}\n"
            
        compaction_prompt = (
            "You are a system summarization utility. Summarize the following educational bash refactoring conversation so far. "
            "List: (1) what issues were identified, (2) which refactors were approved, (3) what Bash rules/lessons were taught. "
            "Keep the summary educational, clear, and under 300 words:\n\n" + transcript
        )
        
        try:
            # We call the model to summarize. We use 'await' because generate_content is an async call.
            # MODEL_ROUTING["compactor"] points to 'gemini-3.5-flash' (cheap/fast model)
            res = await self.client.aio.models.generate_content(
                model=MODEL_ROUTING["compactor"],
                contents=compaction_prompt
            )
            summary_text = res.text
            
            # Rebuild a new starting history that begins with the summary.
            new_history = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=f"Summary of previous educational refactoring steps:\n\n{summary_text}")]
                ),
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="Understood. Let's continue refactoring the script based on this summary.")]
                )
            ]
            # Add the last 4 turns back to the end of the list
            new_history.extend(keep)
            
            # Overwrite the chat's internal history records with the compacted list
            self.teacher_chat._comprehensive_history = new_history
            self.teacher_chat._curated_history = list(new_history)
            
            logger.log_compaction(len(history), len(new_history))
            print("\033[1;34m[System: Compaction completed. History length reduced from {} to {} entries.]\033[0m".format(len(history), len(new_history)))
        except Exception as e:
            print(f"\033[1;31mWarning: History compaction failed: {str(e)}\033[0m")

    async def run(self):
        """Starts and runs the orchestration loop."""
        logger.log_start(self.file_path, MODEL_ROUTING)
        
        # Check if a previous session file exists
        resumed = False
        if os.path.exists(self.session_file):
            choice = input("Previous session found. Resume? [Y/n]: ").strip().lower()
            if choice not in ('n', 'no'):
                # Try to load session
                resumed = await self.load_session()
                
        if resumed:
            print("\033[1;32mResumed previous session. Current Step: {}\033[0m".format(state.state.current_step))
        else:
            # Delete old session files if starting a new session
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                
            # Read target script
            try:
                with open(self.file_path, 'r') as f:
                    content = f.read()
            except Exception as e:
                print(f"\033[1;31mError reading file: {str(e)}\033[0m")
                return

            # Initialize global ScriptState
            state.state = state.ScriptState(self.file_path, content)
            
            # ------------------------------------------------------------------
            # AGENT 1: LINTER AGENT
            # ------------------------------------------------------------------
            # The linter runs first using a fast model (gemini-3.5-flash) to find issues.
            print("\033[1;34m" + "="*80)
            print("Step 1: Running Linter Agent (Model: {})".format(MODEL_ROUTING["linter"]))
            print("="*80 + "\033[0m")
            
            linter_config = types.GenerateContentConfig(
                tools=[tools.get_script_content, tools.run_shellcheck],
                system_instruction=LINTER_SYSTEM_INSTRUCTION,
                temperature=0.0
            )
            
            linter_chat = self.client.chats.create(
                model=MODEL_ROUTING["linter"],
                config=linter_config
            )
            
            prompt = "I have loaded the script file. Call get_script_content and run_shellcheck, then output the structured list of issues."
            logger.log_turn("LinterAgent", "user", prompt, intent="Start lint check")
            
            print("Linter is analyzing script and shellcheck output...")
            # We send the request and 'await' the response.
            linter_res = await linter_chat.send_message(prompt)
            state.state.issues_list = linter_res.text
            
            logger.log_turn("LinterAgent", "model", linter_res.text, intent="Output issues list")
            print("\n\033[1;33m[LINTER ISSUES DETECTED]\033[0m")
            print(state.state.issues_list)
            
            # ------------------------------------------------------------------
            # AGENT 2: REFACTOR TEACHER AGENT
            # ------------------------------------------------------------------
            # Next, we boot up the Teacher Agent using the smart model (gemini-3.1-pro-preview)
            # to guide the refactoring.
            print("\033[1;34m" + "="*80)
            print("Step 2: Starting Interactive Refactor Teacher Agent (Model: {})".format(MODEL_ROUTING["teacher"]))
            print("="*80 + "\033[0m")
            
            teacher_config = types.GenerateContentConfig(
                tools=[
                    tools.get_script_content,
                    tools.propose_refactor,
                    tools.run_shellcheck,
                    tools.verify_script,
                    tools.save_changes,
                ],
                system_instruction=TEACHER_SYSTEM_INSTRUCTION,
                temperature=0.0
            )
            
            self.teacher_chat = self.client.chats.create(
                model=MODEL_ROUTING["teacher"],
                config=teacher_config
            )
            
            # Feed the linter findings to the Teacher Agent to kick off the session
            teacher_prompt = (
                f"Linter Agent found the following issues:\n{state.state.issues_list}\n\n"
                "Please read the script using `get_script_content`, then propose the first improvement."
            )
            logger.log_turn("RefactorTeacherAgent", "user", teacher_prompt, intent="Start teaching/refactoring phase")
            
            teacher_res = await self.teacher_chat.send_message(teacher_prompt)
            logger.log_turn("RefactorTeacherAgent", "model", teacher_res.text, intent="First refactor proposal")
            print("\n\033[1;35mTeacher Response:\033[0m")
            print(teacher_res.text)
            
            # Save the session immediately after starting
            await self.save_session()

        # ----------------------------------------------------------------------
        # MAIN INTERACTIVE LOOP
        # ----------------------------------------------------------------------
        # Loop until the teacher agent calls 'save_changes' (which sets self.completed = True)
        while not state.state.completed:
            try:
                # Prompt the user for input
                user_input = input("\n\033[1;32m[Enter to continue, or type feedback/exit]:\033[0m ").strip()
                
                # Check if the user typed exit
                if user_input.lower() in ('exit', 'quit'):
                    print("\nExiting and saving session state.")
                    await self.save_session()
                    break
                    
                # If they hit enter with no text, we instruct the model to keep refactoring
                if not user_input:
                    user_input = "Please propose the next improvement, or if done, call save_changes."
                
                logger.log_turn("RefactorTeacherAgent", "user", user_input)
                
                # Check if history needs compaction
                await self.compact_history_if_needed()
                
                print("Refactor Teacher is thinking...")
                response = await self.teacher_chat.send_message(user_input)
                logger.log_turn("RefactorTeacherAgent", "model", response.text)
                
                print("\n\033[1;35mTeacher Response:\033[0m")
                print(response.text)
                
                # Save session state after each turn
                await self.save_session()
                
            except (KeyboardInterrupt, EOFError):
                print("\nExiting and saving session state.")
                await self.save_session()
                break

        # If completed, delete the session state file so we don't prompt to resume next time
        if state.state.completed:
            print("\n\033[1;32mRefactoring session successfully completed and saved!\033[0m")
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
