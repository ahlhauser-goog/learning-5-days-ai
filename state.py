# ==============================================================================
# STATE MANAGEMENT MODULE (state.py)
# ==============================================================================
# This module acts as a shared data container (or "global state"). It lets different
# parts of our program (like the tools, the logger, and the orchestrator) access 
# and update the same script data without having to pass it back and forth constantly.

# Import the standard 'os' (Operating System) library. We use this to deal with
# file paths and check if files exist on the computer.
import os

class ScriptState:
    def __init__(self, file_path: str, content: str):
        # We attach variables to 'self' so they are stored inside the object.
        # This stores the absolute path to the file we are refactoring (e.g. /Users/.../script.sh)
        self.file_path = file_path          
        
        # This stores the current, updated content of the script as it gets modified.
        self.content = content              
        
        # This keeps a copy of the original script code so we can display a comparison (diff) later.
        self.original_content = content     
        
        # This is a boolean flag (True or False) indicating whether the refactoring is complete.
        self.completed = False              
        
        # This string will store the list of issues identified by our Linter Agent.
        self.issues_list = ""               
        
        # This tracks which step of the refactoring process we are currently on (starting at 1).
        self.current_step = 1               

# Once we read the bash script file, we will create a new 'ScriptState' object and
# assign it to this variable, making it accessible to all other modules.
state = None
