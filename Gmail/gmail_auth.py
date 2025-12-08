# Gmail/gmail_auth.py
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os
import pickle
import json

class GmailAuth:
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send"
    ]


    def __init__(self, token_file="token_gmail.pkl"):
        # ONLINE: check for environment variable refresh token
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if refresh_token and client_id and client_secret:
            from google.oauth2.credentials import Credentials
            self.creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=self.SCOPES
            )

        self.token_file = token_file
        self.creds = None
        
        # Create a temporary credentials.json in memory
        self.client_config = {
            "installed": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": ["http://localhost:8080/"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

        

    def authenticate(self):
        """
        Authenticate user with Gmail using OAuth 2.0 with automatic browser flow.
        
        Returns:
            googleapiclient.discovery.Resource: Authorized Gmail API service instance.
        """
        # Try to load existing credentials
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "rb") as token:
                    self.creds = pickle.load(token)
            except (EOFError, pickle.UnpicklingError) as e:
                print(f"Error loading token file: {e}. Starting new authentication.")
                os.remove(self.token_file)  # Remove corrupted token file
                self.creds = None

        # If there are no valid credentials, let the user log in
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    print(f"Error refreshing token: {e}")
                    self.creds = None
            
            if not self.creds:
                # Create an in-memory credentials file
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_creds:
                    json.dump(self.client_config, temp_creds)
                    temp_creds_path = temp_creds.name
                
                try:
                    # Use the temporary credentials file for the flow
                    flow = InstalledAppFlow.from_client_secrets_file(
                        temp_creds_path,
                        scopes=self.SCOPES
                    )
                    
                    # This will open the browser automatically
                    self.creds = flow.run_local_server(port=8080)
                    
                    # Save the credentials for future use
                    with open(self.token_file, "wb") as token:
                        pickle.dump(self.creds, token)
                        
                except Exception as e:
                    print(f"Authentication failed: {e}")
                    return None
                finally:
                    # Clean up the temporary file
                    try:
                        os.unlink(temp_creds_path)
                    except:
                        pass

        # Build and return the Gmail API service
        try:
            service = build("gmail", "v1", credentials=self.creds)
            return service
        except Exception as e:
            print(f"Failed to create Gmail service: {e}")
            return None
