# Gmail/gmail_auth.py
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
from dotenv import load_dotenv

# Load environment variables
# Try .envSecrets first (for local development), then fall back to .env or system env vars
load_dotenv('.envSecrets')  # Load .envSecrets if it exists
load_dotenv()  # Also load .env if it exists, and system environment variables override

class GmailAuth:
    """
    Gmail Authentication using environment variables.
    Works on both localhost and Railway without token files.
    """
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send"
    ]

    def __init__(self):
        """Initialize Gmail authentication using environment variables."""
        self.creds = None
        self._load_credentials_from_env()

    def _load_credentials_from_env(self):
        """
        Load credentials from environment variables.
        Requires: GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
        """
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        # Validate required environment variables
        if not refresh_token:
            raise ValueError(
                "GOOGLE_REFRESH_TOKEN environment variable is required. "
                "Please set it in your environment or .env file."
            )
        if not client_id:
            raise ValueError(
                "GOOGLE_CLIENT_ID environment variable is required. "
                "Please set it in your environment or .env file."
            )
        if not client_secret:
            raise ValueError(
                "GOOGLE_CLIENT_SECRET environment variable is required. "
                "Please set it in your environment or .env file."
            )

        try:
            self.creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=self.SCOPES
            )
            # Credentials created with token=None are not valid until refreshed
            # This is expected - we'll refresh in authenticate() method
            print("[GmailAuth] ✅ Credentials loaded from environment variables")
        except Exception as e:
            raise ValueError(
                f"Failed to create Gmail credentials from environment variables: {e}. "
                "Please verify GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, and GOOGLE_CLIENT_SECRET are set correctly."
            )

    def authenticate(self):
        """
        Authenticate user with Gmail using OAuth 2.0 credentials from environment variables.
        Automatically refreshes expired tokens.
        
        Returns:
            googleapiclient.discovery.Resource: Authorized Gmail API service instance.
        
        Raises:
            ValueError: If credentials cannot be loaded or refreshed.
            Exception: If Gmail service creation fails.
        """
        if not self.creds:
            raise ValueError("Gmail credentials not initialized. Check environment variables.")

        # Refresh token if not valid (either expired or never set)
        # When token=None initially, creds.valid will be False, so we always refresh
        if not self.creds.valid:
            if self.creds.refresh_token:
                try:
                    print("[GmailAuth] 🔄 Acquiring/refreshing access token...")
                    self.creds.refresh(Request())
                    print("[GmailAuth] ✅ Token acquired/refreshed successfully")
                except Exception as e:
                    raise ValueError(
                        f"Failed to refresh Gmail access token: {e}. "
                        "Please verify GOOGLE_REFRESH_TOKEN is valid and not revoked. "
                        f"Error details: {str(e)}"
                    ) from e
            else:
                raise ValueError(
                    "Gmail credentials are invalid and cannot be refreshed (no refresh_token). "
                    "Please verify your GOOGLE_REFRESH_TOKEN is set correctly in environment variables."
                )

        # Build and return the Gmail API service
        try:
            service = build("gmail", "v1", credentials=self.creds)
            print("[GmailAuth] ✅ Gmail service initialized successfully")
            return service
        except Exception as e:
            raise Exception(
                f"Failed to create Gmail service: {e}. "
                "Please verify your credentials have the required scopes."
            ) from e
