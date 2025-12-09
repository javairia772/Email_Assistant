# Outlook/outlook_auth.py
import os
from msal import PublicClientApplication, SerializableTokenCache
from dotenv import load_dotenv
import jwt


class OutlookAuth:
    """
    Handles authentication and token management for Microsoft Graph API using MSAL.
    Uses only environment variables - no token cache files.
    Works on both localhost and Railway.
    
    Required environment variables:
    - OUTLOOK_CLIENT_ID
    - OUTLOOK_REFRESH_TOKEN
    - TENANT_ID (optional, defaults to "consumers")
    - OUTLOOK_REDIRECT_URI (optional, for initial token generation only)
    """

    def __init__(self):
        # Load environment variables
        # Try .envSecrets first (for local development), then fall back to .env or system env vars
        load_dotenv('.envSecrets')  # Load .envSecrets if it exists
        load_dotenv()  # Also load .env if it exists, and system environment variables override

        self.client_id = os.getenv("OUTLOOK_CLIENT_ID")
        self.redirect_uri = os.getenv("OUTLOOK_REDIRECT_URI")
        self.tenant_id = os.getenv("TENANT_ID", "consumers")
        self.refresh_token = os.getenv("OUTLOOK_REFRESH_TOKEN")

        # Validate required environment variables
        if not self.client_id:
            raise ValueError(
                "OUTLOOK_CLIENT_ID environment variable is required. "
                "Please set it in your environment or .env file."
            )
        if not self.refresh_token:
            raise ValueError(
                "OUTLOOK_REFRESH_TOKEN environment variable is required. "
                "Please set it in your environment or .env file."
            )

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

        # Use in-memory token cache (not persisted to disk)
        # This works on Railway where file system may be ephemeral
        self.cache = SerializableTokenCache()

        try:
            self.app = PublicClientApplication(
                client_id=self.client_id,
                authority=self.authority,
                token_cache=self.cache,
            )
            print("[OutlookAuth] ✅ MSAL application initialized")
        except Exception as e:
            raise ValueError(
                f"Failed to initialize MSAL application: {e}. "
                "Please verify OUTLOOK_CLIENT_ID and TENANT_ID are correct."
            ) from e

        self.token = None  # access token string

    def get_access_token(self, force_refresh=False) -> str:
        """
        Return a valid access token for Microsoft Graph API using refresh token from environment.
        
        Args:
            force_refresh: If True, forces a token refresh even if current token is valid.
        
        Returns:
            str: Valid access token
        
        Raises:
            ValueError: If authentication fails or refresh token is invalid.
        """
        # Always use refresh token from environment (primary method)
        if self.refresh_token:
            try:
                print("[OutlookAuth] 🔄 Acquiring token using refresh token from environment...")
                result = self.app.acquire_token_by_refresh_token(
                    refresh_token=self.refresh_token,
                    scopes=self.scope
                )
                
                if result and "access_token" in result:
                    self.token = result["access_token"]
                    print("[OutlookAuth] ✅ Access token acquired successfully")
                    
                    # Optional debug info
                    try:
                        claims = jwt.decode(self.token, options={"verify_signature": False})
                        print(f"[OutlookAuth] 🔍 Token audience: {claims.get('aud')}")
                        print(f"[OutlookAuth] 🔍 Token scopes: {claims.get('scp')}")
                    except Exception as e:
                        print(f"[OutlookAuth] ⚠️ Could not decode token: {e}")
                    
                    return self.token
                else:
                    error = result.get("error_description") or result.get("error") or "Unknown error"
                    raise ValueError(
                        f"Failed to acquire access token using refresh token: {error}. "
                        "Please verify OUTLOOK_REFRESH_TOKEN is valid and not revoked."
                    )
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                raise ValueError(
                    f"Outlook authentication failed: {e}. "
                    "Please verify OUTLOOK_REFRESH_TOKEN, OUTLOOK_CLIENT_ID, and TENANT_ID are correct."
                ) from e

        # Fallback: Try silent login if refresh token method fails
        # This requires accounts to be in the in-memory cache from a previous session
        # Note: On Railway, this will typically not work as cache is ephemeral
        accounts = self.app.get_accounts()
        if accounts and not force_refresh:
            try:
                result = self.app.acquire_token_silent(
                    scopes=self.scope,
                    account=accounts[0],
                    force_refresh=force_refresh,
                )
                if result and "access_token" in result:
                    self.token = result["access_token"]
                    print("[OutlookAuth] ✅ Access token acquired via silent authentication")
                    return self.token
            except Exception as e:
                print(f"[OutlookAuth] ⚠️ Silent authentication failed: {e}")

        # If we reach here, authentication failed
        raise ValueError(
            "Outlook authentication failed. "
            "Please verify OUTLOOK_REFRESH_TOKEN, OUTLOOK_CLIENT_ID, and TENANT_ID are set correctly in your environment."
        )
