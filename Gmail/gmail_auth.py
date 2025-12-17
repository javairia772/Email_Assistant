import os
import pickle
import json
from typing import Optional
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

class GmailAuth:
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send"
    ]

    def __init__(self, token_file: str = "token_gmail.pkl"):
        self.token_file = token_file
        self.creds = None

        # Client config from environment variables
        self.client_config = {
            "installed": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": ["http://localhost:8080/"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

    def authenticate(self) -> Optional[object]:
        """
        Authenticate with Gmail API and return a service instance.
        Automatically refreshes access token if expired.
        """
        # Step 1: Load existing credentials if available
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "rb") as token:
                    self.creds = pickle.load(token)
            except (EOFError, pickle.UnpicklingError) as e:
                print(f"[WARN] Corrupted token file: {e}, starting fresh.")
                os.remove(self.token_file)
                self.creds = None

        # Step 2: Refresh token if expired
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                with open(self.token_file, "wb") as token:
                    pickle.dump(self.creds, token)  # Save refreshed token
            except Exception as e:
                print(f"[WARN] Failed to refresh token: {e}")
                self.creds = None

        # Step 3: Perform full OAuth flow if no valid credentials
        if not self.creds or not self.creds.valid:
            flow = InstalledAppFlow.from_client_config(
                self.client_config,
                scopes=self.SCOPES
            )
            # Important: force refresh_token issuance
            self.creds = flow.run_local_server(
                port=8080,
                access_type="offline",
                prompt="consent"
            )

            # Save credentials for future use
            with open(self.token_file, "wb") as token:
                pickle.dump(self.creds, token)

        # Step 4: Build Gmail API service
        try:
            service = build("gmail", "v1", credentials=self.creds)
            return service
        except Exception as e:
            print(f"[ERROR] Failed to create Gmail service: {e}")
            return None
