# Environment Variables Configuration Guide

This project uses environment variables exclusively for authentication to ensure compatibility with Railway deployment. All credentials must be set via environment variables - no token files are used.

## Required Environment Variables

### Gmail Authentication

**Required:**
- `GOOGLE_REFRESH_TOKEN` - OAuth 2.0 refresh token for Gmail API access
- `GOOGLE_CLIENT_ID` - Google OAuth 2.0 client ID
- `GOOGLE_CLIENT_SECRET` - Google OAuth 2.0 client secret

**How to obtain:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app type)
5. Use [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/) to get refresh token:
   - Select scopes:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.send`
   - Authorize and exchange for refresh token

### Outlook Authentication

**Required:**
- `OUTLOOK_CLIENT_ID` - Microsoft Azure App (client) ID
- `OUTLOOK_REFRESH_TOKEN` - OAuth 2.0 refresh token for Microsoft Graph API

**Optional:**
- `TENANT_ID` - Azure AD tenant ID (defaults to "consumers" for personal accounts)
- `OUTLOOK_REDIRECT_URI` - OAuth redirect URI (only needed for initial token generation)

**How to obtain:**
1. Go to [Azure Portal](https://portal.azure.com/)
2. Register a new application in Azure Active Directory
3. Add redirect URI: `http://localhost:8080` (for local) or your Railway URL
4. Grant API permissions:
   - `Mail.Read`
   - `Mail.Send`
   - `Mail.ReadWrite`
   - `User.Read`
   - `offline_access`
5. Use MSAL or Microsoft Graph Explorer to get refresh token

### Google Sheets Authentication

**Option 1: Service Account (Recommended for Railway)**
- `SHEETS_SERVICE_ACCOUNT_JSON` - Base64-encoded service account JSON

**Option 2: OAuth (uses same credentials as Gmail)**
- `GOOGLE_REFRESH_TOKEN` - Same as Gmail (must include Sheets scopes)
- `GOOGLE_CLIENT_ID` - Same as Gmail
- `GOOGLE_CLIENT_SECRET` - Same as Gmail

**How to obtain Service Account:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a service account
3. Download JSON key file
4. Base64 encode it: `cat service-account.json | base64` (Linux/Mac) or use online tool
5. Grant the service account access to your spreadsheet

**Required Scopes for Sheets:**
- `https://www.googleapis.com/auth/spreadsheets`
- `https://www.googleapis.com/auth/drive.file`
- `https://www.googleapis.com/auth/drive`

### AI/LLM Configuration

**Required:**
- `GROQ_API_KEY` - API key from [Groq](https://groq.com/)

**Optional:**
- `GROQ_MODEL` - Model to use (default: `llama-3.3-70b-versatile`)
- `PROVIDER` - AI provider (default: `groq`)

### Application Configuration

**Optional:**
- `MODE` - Environment mode: `development` (default) or `production`
- `PORT` - Server port (default: 8000 for server.py, 8001 for dashboard_server.py)
- `SUMMARY_CACHE_PATH` - Path to summaries cache JSON file (default: `Summaries/summaries_cache.json`)

## Local Development Setup

1. Create a `.envSecrets` file in the project root:
```bash
# Gmail
GOOGLE_REFRESH_TOKEN=your_refresh_token_here
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here

# Outlook
OUTLOOK_CLIENT_ID=your_outlook_client_id_here
OUTLOOK_REFRESH_TOKEN=your_outlook_refresh_token_here
TENANT_ID=consumers

# Google Sheets (Service Account - Recommended)
SHEETS_SERVICE_ACCOUNT_JSON=base64_encoded_service_account_json_here

# AI
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Application
MODE=development
```

2. The `.envSecrets` file is already in `.gitignore` - never commit credentials.

## Railway Deployment Setup

1. Go to your Railway project settings
2. Add all required environment variables in the "Variables" tab
3. For `SHEETS_SERVICE_ACCOUNT_JSON`, paste the base64-encoded string directly (no quotes)
4. Ensure all credentials are set before deploying

**Important:** Railway's file system is ephemeral, so token files won't persist. Always use environment variables.

## Security Best Practices

1. **Never commit credentials** - All `.env*` files are in `.gitignore`
2. **Use Service Accounts for Sheets** - More secure and better for production
3. **Rotate tokens regularly** - Refresh tokens can expire or be revoked
4. **Use Railway secrets** - Railway provides secure variable storage
5. **Limit scopes** - Only request the minimum required API permissions

## Verification

After setting environment variables, verify they're loaded correctly:

```python
import os
from dotenv import load_dotenv
load_dotenv('.envSecrets')

# Check Gmail
print("Gmail:", "✓" if os.getenv("GOOGLE_REFRESH_TOKEN") else "✗")

# Check Outlook  
print("Outlook:", "✓" if os.getenv("OUTLOOK_REFRESH_TOKEN") else "✗")

# Check Sheets
print("Sheets:", "✓" if os.getenv("SHEETS_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_REFRESH_TOKEN") else "✗")

# Check AI
print("Groq:", "✓" if os.getenv("GROQ_API_KEY") else "✗")
```


