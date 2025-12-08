# Outlook/outlook_auth.py
import os
from msal import PublicClientApplication, SerializableTokenCache
from dotenv import load_dotenv
import jwt


class OutlookAuth:
    """
    Handles authentication and token management for Microsoft Graph API using MSAL.
    Supports:
      - Silent login (no repeated browser popups)
      - Token caching and automatic refresh
      - Secure environment variable configuration
    """

    def __init__(self, token_cache_file="msal_outlook_cache.bin"):
        load_dotenv()

        self.client_id = os.getenv("OUTLOOK_CLIENT_ID")
        self.redirect_uri = os.getenv("OUTLOOK_REDIRECT_URI")
        self.tenant_id = os.getenv("TENANT_ID", "consumers")
        self.token_cache_file = token_cache_file

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scope = [
            "User.Read",
            "Mail.Read",
            "Mail.Send",
            "Mail.ReadWrite",
            "Mail.ReadWrite.All",
            "Mail.Send.All",
            "offline_access",
            "openid",
            "profile",
        ]

        # Initialize token cache (persistent)
        self.cache = SerializableTokenCache()
        if os.path.exists(self.token_cache_file):
            try:
                self.cache.deserialize(open(self.token_cache_file, "r").read())
            except Exception:
                self.cache = SerializableTokenCache()  # Reset if corrupt

        self.app = PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self.cache,
        )

        self.token = None  # access token string

    def _save_cache(self):
        """Persist the MSAL cache to disk."""
        if self.cache.has_state_changed:
            with open(self.token_cache_file, "w") as f:
                f.write(self.cache.serialize())

    def get_access_token(self, force_interactive=False, force_refresh=False) -> str:
        """
        Return a valid access token for Microsoft Graph API.
        Automatically handles silent refresh and fallback to interactive login.
        """
        # ONLINE: refresh token from environment
        refresh_token = os.getenv("OUTLOOK_REFRESH_TOKEN")
        if refresh_token and self.client_id and self.tenant_id:
            result = self.app.acquire_token_by_refresh_token(
                refresh_token=refresh_token,
                scopes=self.scope
            )
            if result and "access_token" in result:
                self.token = result["access_token"]
                return self.token

        # Try silent login first (if not forced interactive)
        if not force_interactive:
            accounts = self.app.get_accounts()
            if accounts:
                result = self.app.acquire_token_silent(
                    scopes=self.scope,
                    account=accounts[0],
                    force_refresh=force_refresh,
                )
                if result and "access_token" in result:
                    self.token = result["access_token"]
                    self._save_cache()
                    return self.token

        # Fallback to interactive browser-based login
        result = self.app.acquire_token_interactive(scopes=self.scope)
        if "access_token" in result:
            self.token = result["access_token"]
            self._save_cache()

            # Optional debug info
            try:
                claims = jwt.decode(self.token, options={"verify_signature": False})
                print("🔍 Token audience (aud):", claims.get("aud"))
                print("🔍 Token scopes (scp):", claims.get("scp"))
            except Exception as e:
                print("Could not decode token:", e)

            return self.token

        raise Exception(f"Authentication failed: {result.get('error_description', 'Unknown error')}")
