# ==============================================================================
# SECRET MANAGEMENT MODULE (secrets.py)
# ==============================================================================
# This module is responsible for finding the Gemini API key securely.
# To do this, it checks three different places, going from most secure to least secure:
# 1. Directly in the computer's active environment variables.
# 2. In Google Cloud Secret Manager (a secure cloud database for passwords).
# 3. Inside local environment files ('gemini_key.env' or '.env' text files).

# 'os' allows us to read values from the Operating System's environment variables.
import os

# 'dotenv' is a third-party library that reads text files containing key-value pairs
# (like API keys) and loads them into Python's environment variables.
import dotenv

# We define a function using the 'def' keyword.
# The '-> str' is a return type hint, indicating this function returns a text string.
def get_api_key() -> str:
    """Retrieves the GEMINI_API_KEY.
    
    Checks environment variables, falls back to GCP Secret Manager, and finally
    looks for local .env files.
    """
    
    # --------------------------------------------------------------------------
    # STEP 1: Check if the key is already set directly in the environment.
    # --------------------------------------------------------------------------
    # os.environ is a special dictionary (key-value store) containing all the
    # system's active environment variables.
    # .get("KEY") looks up the key. If it exists, it returns the value. 
    # If it is missing, it returns 'None' instead of crashing.
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ.get("GEMINI_API_KEY")

    # --------------------------------------------------------------------------
    # STEP 2: Try fetching the key from Google Cloud Secret Manager.
    # --------------------------------------------------------------------------
    # We look for a configuration variable 'GCP_PROJECT'. 
    # If the user tells us which Google Cloud project they are using, we try Secret Manager.
    gcp_project = os.environ.get("GCP_PROJECT")
    
    # We set default names for the secret. If GCP_SECRET_NAME isn't specified,
    # we assume the secret is named "GEMINI_API_KEY".
    secret_name = os.environ.get("GCP_SECRET_NAME", "GEMINI_API_KEY")
    
    # We assume we want the latest version of the secret unless specified otherwise.
    secret_version = os.environ.get("GCP_SECRET_VERSION", "latest")
    
    if gcp_project:
        # We use a 'try-except' block. Python runs the code under 'try'.
        # If any error happens (like the library is missing or network fails),
        # instead of crashing the program, Python jumps straight to the 'except' block.
        try:
            # We try to import the Google Cloud Secret Manager client library.
            # This library might not be installed on the user's computer.
            from google.cloud import secretmanager
            
            # Create a client object to connect to Google Cloud services.
            client = secretmanager.SecretManagerServiceClient()
            
            # Format the full identifier path for our cloud secret resource.
            name = f"projects/{gcp_project}/secrets/{secret_name}/versions/{secret_version}"
            
            # Call the Google Cloud API to read the secret values.
            response = client.access_secret_version(request={"name": name})
            
            # The payload contains the secret data in raw bytes. We decode it from UTF-8
            # (binary to text) to get the actual API key string.
            payload = response.payload.data.decode("UTF-8")
            
            if payload:
                # Store the key in our local environment memory so we don't have to fetch it again.
                os.environ["GEMINI_API_KEY"] = payload
                return payload
                
        except ImportError:
            # If the secretmanager package is not installed, an ImportError is raised.
            # We catch it here and pass (do nothing), moving to the next fallback.
            pass
            
        except Exception as e:
            # If any other error occurs (like network failure or wrong project ID),
            # we catch the exception object as 'e', print a warning, and proceed.
            print(f"Warning: Failed to fetch secret from GCP Secret Manager: {str(e)}")

    # --------------------------------------------------------------------------
    # STEP 3: Fall back to local environment files.
    # --------------------------------------------------------------------------
    # We check if a file named 'gemini_key.env' exists in the current folder.
    if os.path.exists("gemini_key.env"):
        # load_dotenv reads the file and populates os.environ with its variables.
        dotenv.load_dotenv("gemini_key.env")
    else:
        # If 'gemini_key.env' doesn't exist, we load the default '.env' file.
        dotenv.load_dotenv()
        
    # Finally, we return whatever key we found. If it's still missing, it returns
    # an empty string ("").
    return os.environ.get("GEMINI_API_KEY", "")
