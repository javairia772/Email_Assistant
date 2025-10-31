# outlook_auth.py
import os
import pickle
from msal import PublicClientApplication, SerializableTokenCache
from dotenv import load_dotenv
import jwt

class OutlookAuth:
    def __init__(self, token_cache_file="msal_outlook_cache.bin"):
        load_dotenv()

        self.client_id = os.getenv("CLIENT_ID")
        self.redirect_uri = os.getenv("REDIRECT_URI")
        self.tenant_id = os.getenv("TENANT_ID", "consumers")
        self.token_cache_file = token_cache_file

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        # MS Graph scopes for delegated access
        self.scope = [
            "https://graph.microsoft.com/User.Read",
            "https://graph.microsoft.com/Mail.Read",
        ]

        # Initialize MSAL token cache
        self.cache = SerializableTokenCache()
        if os.path.exists(self.token_cache_file):
            try:
                self.cache.deserialize(open(self.token_cache_file, "r").read())
            except Exception:
                # Corrupt cache – start fresh
                self.cache = SerializableTokenCache()

        self.app = PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self.cache,
        )

        self.token = None  # access token string (latest)

    def _save_cache(self):
        if self.cache.has_state_changed:
            with open(self.token_cache_file, "w") as f:
                f.write(self.cache.serialize())

    def get_access_token(self, force_interactive: bool = False, force_refresh: bool = False) -> str:
        """Return a valid access token, using cached account if available.
        - force_interactive: skip silent and open browser
        - force_refresh: re-acquire even if cache has token
        """
        # Try silent first (unless forced interactive)
        if not force_interactive:
            accounts = self.app.get_accounts()
            if accounts:
                result = self.app.acquire_token_silent(
                    scopes=self.scope, account=accounts[0], force_refresh=force_refresh
                )
                if result and "access_token" in result:
                    self.token = result["access_token"]
                    self._save_cache()
                    return self.token

        # Fallback to interactive (let MSAL determine redirect uri)
        result = self.app.acquire_token_interactive(scopes=self.scope)
        if "access_token" in result:
            self.token = result["access_token"]
            self._save_cache()

            # Optional: debug claims
            try:
                claims = jwt.decode(self.token, options={"verify_signature": False})
                print("🔍 Token audience (aud):", claims.get("aud"))
                print("🔍 Token scopes (scp):", claims.get("scp"))
            except Exception as e:
                print("Could not decode token:", e)

            return self.token
        else:
            raise Exception(f"Authentication failed: {result.get('error_description', 'Unknown error')}")
