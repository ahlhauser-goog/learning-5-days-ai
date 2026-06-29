# ==============================================================================
# STRUCTURED OBSERVABILITY LOGGING MODULE (logger.py)
# ==============================================================================
# This module implements structured JSON logging. Rather than printing basic text
# to the terminal, it saves logs as "JSON Lines" (one JSON dictionary per line) to a file.
# Crucially, it includes security filters that automatically scan all logged text 
# and redact sensitive information (like Gemini API keys or local home directories).

import os
import re
import json
import datetime
from typing import Any, Dict

# ------------------------------------------------------------------------------
# PII & API KEY REDACTION UTILITIES
# ------------------------------------------------------------------------------
# We compile a regular expression pattern. This matches strings starting with "AIzaSy"
# followed by 33 characters (letters, numbers, underscores, or hyphens).
# This is the standard format for Google API keys.
API_KEY_REGEX = re.compile(r"AIzaSy[A-Za-z0-9_\-]{33}")

def get_user_home() -> str:
    """Returns the absolute path to the current user's home directory.
    
    For example: '/Users/username' on macOS or '/home/username' on Linux.
    """
    return os.path.expanduser("~")

def redact_pii(text: str) -> str:
    """Scans text and replaces any sensitive secrets with safe placeholder values."""
    # If the input is not a text string, we return it immediately as-is.
    if not isinstance(text, str):
        return text
    
    # .sub() is a regular expression function that finds all instances matching
    # our API_KEY_REGEX pattern and replaces (substitutes) them with "[REDACTED_API_KEY]".
    text = API_KEY_REGEX.sub("[REDACTED_API_KEY]", text)
    
    # Find the current user's home folder path (e.g. '/Users/ahlhauser')
    home_dir = get_user_home()
    
    # We only perform replacement if a valid home folder is found and it is not the root directory.
    if home_dir and home_dir != "/":
        text = text.replace(home_dir, "[USER_HOME]")
        
    return text

# ------------------------------------------------------------------------------
# STRUCTURED LOGGER CLASS
# ------------------------------------------------------------------------------
class StructuredLogger:
    # Constructor function that sets the name of the log file.
    # If no file name is specified when we create the logger, it defaults to "agent_run.jsonl".
    def __init__(self, log_file: str = "agent_run.jsonl"):
        self.log_file = log_file

    # An internal helper function (starting with an underscore by convention)
    # that handles formatting, redacting, and writing the log entries.
    def _write_log(self, agent: str, event: str, data: Dict[str, Any]):
        # Construct a dictionary representing our log entry.
        log_entry = {
            # datetime.datetime.now(datetime.timezone.utc).isoformat() creates a standard
            # UTC timestamp string like: "2026-06-29T20:30:00.000000+00:00"
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            # Name of the agent writing this log (e.g., LinterAgent or RefactorTeacherAgent)
            "agent": agent,
            # Name of the event being logged (e.g., "tool_call" or "policy_check")
            "event": event,
            # Additional details (arguments, responses, or diffs)
            "data": data
        }
        
        # 1. Convert the python log dictionary into a raw JSON text string.
        serialized = json.dumps(log_entry)
        
        # 2. Run our redaction function on the JSON text string to clean any secrets.
        redacted_serialized = redact_pii(serialized)
        
        # 3. Convert the clean JSON text string back into a Python dictionary.
        redacted_entry = json.loads(redacted_serialized)
        
        # 4. Open the log file in append mode ("a").
        # Append mode creates the file if it does not exist, and adds new lines
        # to the end of the file rather than overwriting what's already there.
        # 'with open' makes sure the file is safely closed when we are finished writing.
        with open(self.log_file, "a") as f:
            # We convert the redacted dictionary to JSON text and write it,
            # appending a newline character ("\n") so each log is on its own line.
            f.write(json.dumps(redacted_entry) + "\n")

    # The following public functions are clean wrapper methods for different events,
    # making it easy to log specific agent actions throughout the code.

    def log_start(self, file_path: str, model_routing: Dict[str, str]):
        """Logs when the agent starts refactoring a file."""
        self._write_log("Orchestrator", "start", {
            "file_path": file_path,
            "model_routing": model_routing
        })

    def log_turn(self, agent: str, role: str, message: str, intent: str = None):
        """Logs a single conversational turn (user input or agent thought/output)."""
        self._write_log(agent, "chat_turn", {
            "role": role,
            "message": message,
            "intent": intent
        })

    def log_tool_call(self, agent: str, tool_name: str, args: Dict[str, Any]):
        """Logs when the agent calls a tool function."""
        self._write_log(agent, "tool_call", {
            "tool_name": tool_name,
            "arguments": args
        })

    def log_tool_response(self, agent: str, tool_name: str, response: str, outcome: str = None):
        """Logs what the tool returned and if it was successful."""
        self._write_log(agent, "tool_response", {
            "tool_name": tool_name,
            "response": response,
            "outcome": outcome
        })

    def log_policy_check(self, success: bool, reason: str, details: Dict[str, Any]):
        """Logs when the PolicyGuardrail evaluates a code proposal."""
        self._write_log("PolicyGuardrail", "policy_check", {
            "success": success,
            "reason": reason,
            "details": details
        })

    def log_compaction(self, original_length: int, new_length: int):
        """Logs when the conversation history is summarized to save context space."""
        self._write_log("Orchestrator", "history_compaction", {
            "original_length": original_length,
            "new_length": new_length
        })

    def log_session_save(self, session_file: str, success: bool, error: str = None):
        """Logs if the session state was successfully saved to disk."""
        self._write_log("Orchestrator", "session_save", {
            "session_file": session_file,
            "success": success,
            "error": error
        })

    def log_session_load(self, session_file: str, success: bool, error: str = None):
        """Logs if the session state was successfully restored from disk."""
        self._write_log("Orchestrator", "session_load", {
            "session_file": session_file,
            "success": success,
            "error": error
        })
