# Gmail/gmail_auth.py
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle
import os

class GmailAuth:
    SCOPES = [ "https://www.googleapis.com/auth/gmail.readonly","https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]
    def __init__(self, credentials_file="credentials.json", token_file="token_gmail.pkl"):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.creds = None

    def authenticate(self):
        """Authenticate user with Gmail and return a service client."""
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                self.creds = pickle.load(token)

        if not self.creds or not self.creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
            self.creds = flow.run_local_server(port=8080)
            with open(self.token_file, "wb") as token:
                pickle.dump(self.creds, token)

        service = build("gmail", "v1", credentials=self.creds)
        return service
