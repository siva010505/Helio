import os
import sys

# Ensure we can import from src when running from the root directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

from src.youtube.oauth import get_authenticated_service

if __name__ == "__main__":
    print("Starting authentication flow...")
    print("A browser window should open. Please approve ALL requested permissions.")
    
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    client_secret_file = "client_secret.json"
    token_file = "token.pickle"
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            youtube_config = config.get("youtube", {})
            client_secret_file = youtube_config.get("client_secret_file", client_secret_file)
            token_file = youtube_config.get("token_file", token_file)
            
    # Resolve relative paths from project root
    project_root = os.path.abspath(os.path.dirname(__file__) + '/..')
    client_secret_file = os.path.normpath(os.path.join(project_root, client_secret_file))
    token_file = os.path.normpath(os.path.join(project_root, token_file))
    
    print(f"Using Client Secret: {client_secret_file}")
    print(f"Using Token File: {token_file}")
    
    # This will trigger the OAuth flow if token.pickle doesn't exist or is invalid
    creds = get_authenticated_service(credentials_file=client_secret_file, token_file=token_file)
    
    if creds and creds.valid:
        print("\nSUCCESS! A brand new token.pickle has been generated.")
        print("You can now convert it to Base64 and update your GitHub Secrets if necessary.")
    else:
        print("\nERROR: Failed to generate token.pickle.")
