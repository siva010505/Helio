"""
Phase 7 Smoke Test.
Tests UploadAgent authentication flow.
Requires client_secret.json to be present in the project root.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

from src.config_loader import load_config
from src.agents.upload_agent import UploadAgent

def main():
    config = load_config()
    ch_cfg = config["channels"][0]

    print("\n[TEST] 1. Initialising UploadAgent...")
    uploader = UploadAgent(config)
    
    # We will just test authentication.
    print("\n[TEST] 2. Testing YouTube OAuth Authentication...")
    try:
        creds = uploader._authenticate()
        if creds and creds.valid:
            print("[PASS] Successfully authenticated with YouTube API!")
        else:
            print("[FAIL] Authentication returned invalid credentials.")
    except FileNotFoundError as e:
        print("\n[SKIP] client_secret.json not found.")
        print("To fully enable YouTube uploads, you must:")
        print("1. Go to Google Cloud Console (console.cloud.google.com).")
        print("2. Create a new project and enable the 'YouTube Data API v3'.")
        print("3. Create an OAuth 2.0 Client ID (Desktop App).")
        print("4. Download the JSON file and save it as 'client_secret.json' in the root directory.")
        
    print("\n=======================================================")
    print("  Phase 7 Smoke Test: DONE")
    print("=======================================================")

if __name__ == "__main__":
    main()
