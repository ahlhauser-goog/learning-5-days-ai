#!/usr/bin/env python3

# === 1. IMPORTING LIBRARIES (DEPENDENCIES) ===
# Imports let us use code written by others or built into Python.
import os          # Operating System library: lets us check files, read paths, etc.
import sys         # System library: lets us read command-line arguments and exit the script.
import difflib     # Diff library: helps us compare two pieces of text and show differences.
import subprocess  # Subprocess library: lets us run external terminal commands (like shellcheck).
import tempfile    # Tempfile library: lets us create temporary files that delete themselves later.
import dotenv      # Dotenv library: reads key-value pairs from a text file and sets them as environment variables.

# === 2. LOADING CONFIGURATION & API KEYS ===
# We look for a file named "gemini_key.env" first.
# If it exists, we load its variables (like GEMINI_API_KEY) into Python's environment.
# If it doesn't, we try to load the default ".env" file.
if os.path.exists("gemini_key.env"):
    dotenv.load_dotenv("gemini_key.env")
else:
    dotenv.load_dotenv()

# We check if the GEMINI_API_KEY environment variable is set.
# os.environ is a dictionary (key-value store) containing all environment variables.
# .get() looks up the key. If it's missing, it returns None.
if not os.environ.get("GEMINI_API_KEY"):
    print("\033[1;31mError: GEMINI_API_KEY is not set.\033[0m") # Prints error in red
    print("Please set it in a 'gemini_key.env' file or your shell environment:")
    print("  GEMINI_API_KEY=your_key_here")
    sys.exit(1)

# Try to import the Google GenAI SDK.
# Using a "try-except" block allows us to catch the ImportError if the library
# is not installed, and print a helpful message instead of a messy traceback crash.
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("\033[1;31mError: google-genai package not found.\033[0m")
    print("Please activate your virtual environment (.venv) or check your python interpreter.")
    sys.exit(1)

# === 3. MANAGING SCRIPT STATE ===
class ScriptState:
    def __init__(self, file_path: str, content: str):
        self.file_path = file_path          # The path of the file we are refactoring (e.g. ~/.bash_functions)
        self.content = content              # The current, updated code of the script
        self.original_content = content    # A backup of the code before we made any changes
        self.completed = False              # We set this to True when we are done and ready to exit

# We declare a global variable "state" and set it to None.
# When the script runs, we will overwrite this with our ScriptState object.
state = None

# === 4. CUSTOM TOOLS (FUNCTIONS FOR THE AI AGENT) ===
# These python functions will be handed to the Gemini AI. 
# Gemini can analyze their docstrings (the text inside triple quotes) to understand 
# when and how to call them.

def get_script_content() -> str:
    """Returns the current content of the script being refactored.
    
    Always call this tool to see the current state of the script.
    """
    # Simply returns the current code stored in our global state object
    return state.content

def propose_refactor(explanation: str, lesson_summary: str, refactored_code: str) -> str:
    """Proposes a single refactoring change to the user.
    
    Args:
        explanation: A clear, educational explanation of the issue and the proposed fix.
        lesson_summary: A summary of the Bash concepts/rules taught by this change.
        refactored_code: The complete new content of the script after applying this change.
    """
    # .splitlines(keepends=True) splits the long string of code into a list of individual lines.
    # keepends=True preserves the newline characters (\n) at the end of each line, which difflib needs.
    old_lines = state.content.splitlines(keepends=True)
    new_lines = refactored_code.splitlines(keepends=True)
    
    # programmatically calculate the differences between the old lines and the new lines.
    diff_generator = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=os.path.basename(state.file_path),
        tofile=os.path.basename(state.file_path) + " (proposed)"
    )
    # Join the list of diff lines back into a single long string
    diff_text = "".join(diff_generator)
    
    # If the diff text is empty (or just whitespace), it means the AI didn't actually change anything.
    if not diff_text.strip():
        return "No changes were detected in the proposed refactored_code compared to the current content."
    
    # Print the proposal with visual delimiters and colors.
    # "\033[..." are ANSI escape sequences. They change the text style/color in the terminal.
    #   \033[1;36m = Bold Cyan
    #   \033[1;33m = Bold Yellow
    #   \033[1;32m = Bold Green
    #   \033[0m    = Reset all formatting back to default
    print("\n" + "="*80)
    print("\033[1;36m[PROPOSED REFACTOR]\033[0m")
    print(explanation)
    print("-"*80)
    print("\033[1;33m[DIFF]\033[0m")
    
    # Loop over the diff line-by-line and colorize it like a real git diff
    for line in diff_text.splitlines():
        if line.startswith('+') and not line.startswith('+++'):
            print(f"\033[32m{line}\033[0m") # Green for added lines
        elif line.startswith('-') and not line.startswith('---'):
            print(f"\033[31m{line}\033[0m") # Red for deleted lines
        elif line.startswith('@@'):
            print(f"\033[36m{line}\033[0m") # Cyan for location headers
        else:
            print(line) # Normal white for context lines
            
    print("-"*80)
    print("\033[1;32m[LESSON SUMMARY]\033[0m")
    print(lesson_summary)
    print("="*80)
    
    # Start a loop to prompt the user. It will continue looping until they enter y or n.
    while True:
        try:
            # input() waits for the user to type something and press Enter.
            # .strip() removes leading/trailing spaces.
            # .lower() converts it to lowercase so 'Y' and 'y' are treated the same way.
            choice = input("\nApply this refactor? [y/N]: ").strip().lower()
            if choice in ('y', 'yes'):
                state.content = refactored_code # Save the new code into memory
                return "Refactor applied. Now run shellcheck or verify_script to validate it."
            elif choice in ('n', 'no', ''):
                return "Refactor rejected by user. Please propose an alternative or discuss with the user."
            else:
                print("Please enter 'y' or 'n'.")
        except (KeyboardInterrupt, EOFError):
            # Handles if the user presses Ctrl+C or Ctrl+D in their terminal to quit
            print("\nAborted.")
            sys.exit(0)

def run_shellcheck() -> str:
    """Runs shellcheck on the current script content to verify it.
    
    Returns the shellcheck warnings/errors, or a success message if clean.
    """
    # Create a temporary file to write the current code into, so shellcheck can read it.
    # NamedTemporaryFile handles creating the file safely. delete=False prevents it
    # from being deleted immediately when we close it.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
        temp_file.write(state.content)
        temp_file_path = temp_file.name # Get the absolute file path on disk
        
    try:
        # Run the shellcheck command as an external process.
        # We pass it as a list of strings: ['command', 'arg1', 'arg2', ...]
        # stdout=PIPE and stderr=PIPE capture the outputs so they don't print directly to terminal.
        # text=True decodes the output binary into a standard Python string.
        result = subprocess.run(
            ['shellcheck', '-s', 'bash', temp_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Manually delete the temporary file after running the command
        os.unlink(temp_file_path)
        
        # returncode is the exit code of the process. 0 means success (no issues found).
        if result.returncode == 0:
            return "shellcheck passed with no issues."
        else:
            # Replace the weird temporary file name in the output with the actual script name.
            output = result.stdout.replace(temp_file_path, os.path.basename(state.file_path))
            return f"shellcheck found the following issues:\n{output}"
            
    except FileNotFoundError:
        # If the shellcheck binary is not installed on the system path
        os.unlink(temp_file_path)
        return "shellcheck command not found. Please install it with 'brew install shellcheck'."

def verify_script(command_to_run: str) -> str:
    """Runs a test command using the current script state.
    
    This writes the current script content to a temporary file and runs:
    bash -c "source <temp_file> && <command_to_run>"
    
    Args:
        command_to_run: The command to execute (e.g. "my_func arg1 arg2").
    """
    # Security prompt before running any user commands!
    print("\n" + "="*80)
    print("\033[1;31m[SECURITY NOTICE: EXECUTION REQUEST]\033[0m")
    print(f"The agent wants to run the following test command in Bash:")
    print(f"  source {os.path.basename(state.file_path)} && {command_to_run}")
    print("="*80)
    
    # Prompt the user for approval
    while True:
        try:
            choice = input("Allow execution? [y/N]: ").strip().lower()
            if choice in ('y', 'yes'):
                break
            elif choice in ('n', 'no', ''):
                return "Execution denied by user."
            else:
                print("Please enter 'y' or 'n'.")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
            
    # Write the script code in memory to a temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
        temp_file.write(state.content)
        temp_file_path = temp_file.name
        
    try:
        # Construct the execution command.
        # We source the temp file first to load the functions, then execute the command.
        cmd = f"source {temp_file_path} && {command_to_run}"
        result = subprocess.run(
            ['bash', '-c', cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10 # If the script hangs or runs forever, kill it after 10 seconds
        )
        os.unlink(temp_file_path) # Clean up the temp file
        
        # Format stdout and stderr logs nicely
        output = []
        if result.stdout:
            output.append(f"--- STDOUT ---\n{result.stdout}")
        if result.stderr:
            output.append(f"--- STDERR ---\n{result.stderr}")
        
        status = f"Exit Code: {result.returncode}"
        output.append(status)
        
        return "\n".join(output)
        
    except subprocess.TimeoutExpired:
        os.unlink(temp_file_path)
        return "Execution timed out after 10 seconds."
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        return f"Error executing command: {str(e)}"

def save_changes() -> str:
    """Saves the final refactored script back to its original file path.
    
    Call this tool only when the user confirms they are happy with all changes.
    """
    try:
        # Open the file at self.file_path in write mode ('w').
        # 'with open' guarantees that the file is closed automatically when we finish.
        with open(state.file_path, 'w') as f:
            f.write(state.content)
        state.completed = True # Mark the state as completed so the main loop stops
        return f"Successfully saved all changes to {state.file_path}."
    except Exception as e:
        return f"Failed to save changes to {state.file_path}: {str(e)}"


# === 5. SYSTEM INSTRUCTIONS FOR THE GEMINI AGENT ===
# These instructions define the persona, rules, and workflow constraints
# that the Gemini model will follow during the conversation.
SYSTEM_INSTRUCTIONS = """
You are an expert Bash scripting teacher and developer. Your goal is to help the user improve their shell scripts, functions, and aliases in a step-by-step, educational manner.

You have access to the following tools:
1. `get_script_content`: Get the current content of the script.
2. `propose_refactor`: Propose a single refactor.
3. `run_shellcheck`: Run shellcheck on the current state.
4. `verify_script`: Run a command using the current state.
5. `save_changes`: Write the final content back to the original file.

CRITICAL RULES FOR REFACTORING:
- Always call `get_script_content` first to see the script.
- Propose EXACTLY ONE refactor at a time. Do not try to clean the entire script in one go.
- Explain the basic bash syntax concepts involved in your proposal (e.g. explain local variables, quoting variables, brackets).
- Focus on making the script modular, removing duplicate logic, adding verbose comments, and implementing a `-v` (verbose) logging flag in functions where it makes sense.
- After a refactor is applied (propose_refactor returns Success), run `run_shellcheck` to verify syntax. If shellcheck flags warnings or errors, explain them and propose a fix.
- Ask the user if they'd like to test the refactored logic with `verify_script` by providing an appropriate test invocation command.
- Once an improvement is completely finished, checked, and tested, move to the next improvement.
- When there are no further improvements to make and the user is fully satisfied, call `save_changes` to save the script and finish the session.
"""

# === 6. MAIN EXECUTION LOOP ===
def run_agent():
    global state
    # sys.argv is a list of command line arguments passed to the script.
    # sys.argv[0] is always the name of this python file itself ('improve.py').
    # sys.argv[1] is the first argument (which should be the path of the script).
    if len(sys.argv) < 2:
        print("\033[1;31mUsage: python improve.py <path_to_bash_script>\033[0m")
        sys.exit(1)
        
    # Get the absolute, full path of the target file
    file_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(file_path):
        print(f"\033[1;31mError: File '{file_path}' does not exist.\033[0m")
        sys.exit(1)
        
    try:
        # Read the initial content of the script
        with open(file_path, 'r') as f:
            initial_content = f.read()
    except Exception as e:
        print(f"\033[1;31mError reading file: {str(e)}\033[0m")
        sys.exit(1)
        
    # Create our global state object
    state = ScriptState(file_path, initial_content)
    
    print("\033[1;34m" + "="*80)
    print(f"Starting Bash Refactoring Agent on file: {os.path.basename(file_path)}")
    print("Type 'exit' or 'quit' at any prompt to exit the loop.")
    print("="*80 + "\033[0m")
    
    # Configure the Google GenAI Client with our API Key
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    # Define generating options and register our custom Python functions as tools
    config = types.GenerateContentConfig(
        tools=[
            get_script_content,
            propose_refactor,
            run_shellcheck,
            verify_script,
            save_changes,
        ],
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=0.0 # 0.0 temperature makes the model output deterministic and stable
    )
    
    # Create the chat session
    chat = client.chats.create(
        model='gemini-3.5-flash',
        config=config
    )
    
    # Prompt the agent to start by reading and checking the script content
    prompt = (
        "I have loaded the script file. Please call `get_script_content` to read it, "
        "then run `run_shellcheck` to inspect it. After that, propose the first improvement."
    )
    
    try:
        # send_message sends the prompt to Gemini. 
        # The GenAI SDK automatically calls any tools (our Python functions) requested by Gemini,
        # feeds their output back to Gemini, and repeats until Gemini decides to output a final text answer.
        response = chat.send_message(prompt)
        print("\n\033[1;35mAgent Response:\033[0m")
        print(response.text)
    except Exception as e:
        print(f"\033[1;31mAgent initialization error: {str(e)}\033[0m")
        return
        
    # Keep looping while state.completed is False
    while not state.completed:
        try:
            # Prompt the user for input. If they just press Enter, we tell the agent to keep going.
            user_input = input("\n\033[1;32m[Enter to continue, or type feedback/exit]:\033[0m ").strip()
            
            # Allow exiting early
            if user_input.lower() in ('exit', 'quit'):
                print("\nExiting refactoring agent.")
                break
                
            # If they pressed Enter with no text, we instruct the model to move to the next step
            if not user_input:
                user_input = "Please propose the next improvement, or if done, call save_changes."
                
            # Send the user response or prompt to Gemini and print the answer
            response = chat.send_message(user_input)
            print("\n\033[1;35mAgent Response:\033[0m")
            print(response.text)
            
        except (KeyboardInterrupt, EOFError):
            print("\nExiting refactoring agent.")
            break
            
    print("\n\033[1;34m" + "="*80)
    print("Refactoring session ended.")
    print("="*80 + "\033[0m")

# This is a Python standard boilerplate.
# It makes sure run_agent() only executes if this file is run directly (e.g. `python improve.py`),
# and NOT if it is imported into another Python file.
if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
