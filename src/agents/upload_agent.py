"""
Upload Agent

Role:
Handles authenticating with the YouTube Data API v3 using OAuth2.
Uploads the final assembled video and sets the SEO metadata and thumbnail.
"""

import os
import pickle
import logging
from typing import Dict, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class UploadAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.credentials_file = self.config.get("youtube", {}).get("client_secret_file", "client_secret.json")
        self.token_file = "token.pickle"
        
    def _authenticate(self):
        """
        Authenticates the user using OAuth2.
        Returns a googleapiclient credentials object.
        """
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
                
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning("Could not refresh token, forcing re-auth: %s", e)
                    creds = None
                    
            if not creds:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(f"OAuth Client Secrets file '{self.credentials_file}' not found. Please download it from Google Cloud Console.")
                
                # Launch local server for user to sign in
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
                
            # Save the credentials for the next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
                
        return creds

    def upload_video(self, video_path: str, title: str, description: str, tags: list, thumbnail_path: str = None) -> str:
        """
        Uploads the video to YouTube.
        Returns the new YouTube Video ID.
        """
        logger.info("[UploadAgent] Starting authentication for YouTube API...")
        try:
            creds = self._authenticate()
        except FileNotFoundError as e:
            logger.error("[UploadAgent] %s", e)
            raise
            
        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '22'  # People & Blogs
            },
            'status': {
                'privacyStatus': 'public',  # Upload publicly to reach audience
                'selfDeclaredMadeForKids': False, 
            }
        }

        # Call the API's videos.insert method to create and upload the video.
        logger.info("[UploadAgent] Uploading video file '%s'...", video_path)
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')
        
        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("[UploadAgent] Uploaded %d%%", int(status.progress() * 100))
                
        video_id = response.get('id')
        logger.info("[UploadAgent] Video uploaded successfully! Video ID: %s", video_id)

        # Upload thumbnail if provided and supported
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                logger.info("[UploadAgent] Uploading custom thumbnail...")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
                logger.info("[UploadAgent] Thumbnail uploaded successfully.")
            except Exception as e:
                # Often fails if the channel hasn't verified their phone number
                logger.warning("[UploadAgent] Failed to upload thumbnail (account might not have custom thumbnails enabled): %s", e)

        return video_id
