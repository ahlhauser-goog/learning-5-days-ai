#!/usr/bin/env python3
# ==============================================================================
# ENTRY POINT MODULE (improve.py)
# ==============================================================================
# This is the main script that starts the program. 
# It reads command-line arguments, retrieves the Gemini API key, configures 
# the GenAI client, and runs the asynchronous agent orchestrator loop.

import os
import sys
import asyncio
from google import genai
from secrets import get_api_key
from orchestrator import AgentOrchestrator

def main():
    # 'sys.argv' is a list in Python that contains all the command line arguments
    # passed to this script.
    # sys.argv[0] is always the name of this file itself (e.g. 'improve.py').
    # sys.argv[1] is the first argument after the filename (which should be the bash script path).
    # If the user didn't provide enough arguments, len(sys.argv) will be less than 2.
    if len(sys.argv) < 2:
        print("\033[1;31mUsage: python improve.py <path_to_bash_script>\033[0m")
        sys.exit(1) # Exit with code 1, which tells the terminal the program failed.
        
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"\033[1;31mError: File '{file_path}' does not exist.\033[0m")
        sys.exit(1)

    # 1. Fetch the API key (Secret Manager with local fallback)
    api_key = get_api_key()
    if not api_key:
        print("\033[1;31mError: GEMINI_API_KEY is not set.\033[0m")
        print("Please set it in a 'gemini_key.env' file, environment, or GCP Secret Manager.")
        sys.exit(1)

    # 2. Configure the Google GenAI Client with our API Key
    client = genai.Client(api_key=api_key)
    
    # 3. Instantiate our orchestrator class
    orchestrator = AgentOrchestrator(file_path, client)
    
    # 4. Start the asynchronous loop
    try:
        # 'asyncio.run' is the standard way to run an asynchronous coroutine from a synchronous main function.
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        # Catch if the user hits Ctrl+C to terminate the program
        print("\nAborted.")
        sys.exit(0) # Exit code 0 means the program completed successfully.

# This is the Python standard boilerplate.
# It makes sure the 'main()' function only executes if this file is run directly
# (e.g., by executing `python improve.py`), and NOT if it is imported as a library
# into another python file.
if __name__ == "__main__":
    main()
