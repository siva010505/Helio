import os
import pickle
import logging
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# Combined scopes for both Upload and Analytics agents
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]

def get_authenticated_service(credentials_file="client_secret.json", token_file="token.pickle"):
    """
    Authenticates the user using OAuth2 and requests the union of all required scopes.
    Returns a googleapiclient credentials object.
    """
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Could not refresh token, forcing re-auth: %s", e)
                creds = None
                
        if not creds:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(f"OAuth Client Secrets file '{credentials_file}' not found. Please download it from Google Cloud Console.")
            
            # Launch local server for user to sign in
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
            
    return creds
