# outlook_auth.py
import os
from msal import PublicClientApplication
from dotenv import load_dotenv
import jwt

class OutlookAuth:
    def __init__(self):
        load_dotenv()

        self.client_id = os.getenv("CLIENT_ID")
        self.redirect_uri = os.getenv("REDIRECT_URI")
        self.tenant_id = os.getenv("TENANT_ID", "consumers")

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scope = [
            "https://graph.microsoft.com/User.Read",
            "https://graph.microsoft.com/Mail.Read"
        ]

        self.token = None

    def authenticate(self):
        app = PublicClientApplication(self.client_id, authority=self.authority)
        result = app.acquire_token_interactive(scopes=self.scope)

        if "access_token" in result:
            self.token = result["access_token"]
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
            raise Exception("Authentication failed:", result.get("error_description"))
        
        
    def get_access_token(self):
        """Return existing token or trigger authentication if missing."""
        if not self.token:
            return self.authenticate()
        return self.token
