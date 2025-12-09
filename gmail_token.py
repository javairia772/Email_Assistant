# ============================================================================
# DISABLED: Token Generation Script
# ============================================================================
# This file has been disabled because the project now uses environment variables
# exclusively for authentication, compatible with Railway deployment.
#
# To get refresh tokens for local development and Railway:
# 
# For Gmail:
# 1. Use Google OAuth 2.0 Playground: https://developers.google.com/oauthplayground/
# 2. Select Gmail API scopes: 
#    - https://www.googleapis.com/auth/gmail.readonly
#    - https://www.googleapis.com/auth/gmail.modify
#    - https://www.googleapis.com/auth/gmail.send
# 3. Authorize and get the refresh token
# 4. Set GOOGLE_REFRESH_TOKEN environment variable
#
# For Outlook:
# 1. Use Microsoft Graph Explorer or MSAL library for initial authorization
# 2. Get the refresh token from the OAuth flow
# 3. Set OUTLOOK_REFRESH_TOKEN environment variable
#
# For Google Sheets (Service Account - Recommended):
# 1. Create a service account in Google Cloud Console
# 2. Download the JSON key file
# 3. Base64 encode it: `cat service-account.json | base64`
# 4. Set SHEETS_SERVICE_ACCOUNT_JSON environment variable
#
# ============================================================================

# Code below is disabled - uncomment only if you need to extract tokens from existing files
# This should only be run locally, not on Railway

# import pickle
# from google.oauth2.credentials import Credentials

# # Path to your token file
# with open("token_gmail.pkl", "rb") as f:
#     creds = pickle.load(f)

# # creds should be a google.oauth2.credentials.Credentials object
# print("Refresh Token:", creds.refresh_token)  # Optional: inspect the token
