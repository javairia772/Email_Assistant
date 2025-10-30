# outlook_auth.py
import os
import pickle
from msal import PublicClientApplication
from dotenv import load_dotenv
import jwt

class OutlookAuth:
    def __init__(self, token_file="token_outlook.pkl"):
        load_dotenv()

        self.client_id = os.getenv("CLIENT_ID")
        self.redirect_uri = os.getenv("REDIRECT_URI")
        self.tenant_id = os.getenv("TENANT_ID", "consumers")
        self.token_file = token_file

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scope = [
            "https://graph.microsoft.com/User.Read",
            "https://graph.microsoft.com/Mail.Read"
        ]

        self.token = None
        self._load_token()

    def _load_token(self):
        """Load cached token from disk if available."""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "rb") as f:
                    cached = pickle.load(f)
                    self.token = cached.get("access_token")
                    # Check if token is expired (basic check via claims)
                    if self.token:
                        try:
                            claims = jwt.decode(self.token, options={"verify_signature": False})
                            import time
                            exp = claims.get("exp", 0)
                            if exp and exp < time.time():
                                print("Cached Outlook token expired, will re-authenticate")
                                self.token = None
                            else:
                                print("Loaded cached Outlook token")
                        except Exception:
                            print("Loaded cached Outlook token (could not verify expiration)")
            except Exception as e:
                print(f"Could not load cached token: {e}")

    def _save_token(self, token_data):
        """Save token to disk for future use."""
        try:
            with open(self.token_file, "wb") as f:
                pickle.dump(token_data, f)
        except Exception as e:
            print(f"Could not save token: {e}")

    def authenticate(self):
        # If we have a cached token, try to use it first
        if self.token:
            return self.token

        app = PublicClientApplication(self.client_id, authority=self.authority)
        
        # Try to get accounts from cache first
        accounts = app.get_accounts()
        
        # Try silent token acquisition if we have accounts
        result = None
        if accounts:
            result = app.acquire_token_silent(scopes=self.scope, account=accounts[0])
        
        # If silent fails, do interactive auth
        if not result or "access_token" not in result:
            print("Attempting interactive authentication (this will open a browser)...")
            result = app.acquire_token_interactive(scopes=self.scope)

        if "access_token" in result:
            self.token = result["access_token"]
            self._save_token(result)  # Cache the token
            print("Authentication successful")

            # Optional: debug claims
            try:
                claims = jwt.decode(self.token, options={"verify_signature": False})
                print("🔍 Token audience (aud):", claims.get("aud"))
                print("🔍 Token scopes (scp):", claims.get("scp"))
            except Exception as e:
                print("Could not decode token:", e)

            return self.token
        else:
            error_msg = result.get("error_description", "Unknown error")
            raise Exception(f"Authentication failed: {error_msg}")
