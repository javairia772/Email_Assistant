# Deployment Errors and Prevention Guide

This document lists all possible errors that can occur during Railway deployment (and local development) and how to prevent them.

## Authentication Errors

### 1. Missing Environment Variables

**Error Messages:**
- `GOOGLE_REFRESH_TOKEN environment variable is required`
- `OUTLOOK_CLIENT_ID environment variable is required`
- `Failed to create Gmail credentials from environment variables`

**Cause:** Required environment variables are not set in Railway or `.envSecrets` file.

**Prevention:**
- ✅ Verify all required variables are set in Railway project settings
- ✅ Check variable names match exactly (case-sensitive)
- ✅ Use `ENV_VARIABLES.md` as a checklist
- ✅ Test locally with `.envSecrets` file before deploying

**Solution:**
1. Go to Railway project → Variables tab
2. Add missing environment variables
3. Redeploy the service

---

### 2. Invalid Refresh Token

**Error Messages:**
- `Failed to refresh Gmail access token`
- `Failed to acquire access token using refresh token`
- `Gmail credentials are invalid and cannot be refreshed`

**Cause:** Refresh token is expired, revoked, or incorrectly copied.

**Prevention:**
- ✅ Ensure refresh token includes all required scopes
- ✅ Verify token hasn't been revoked in Google/Microsoft console
- ✅ Copy token exactly (no extra spaces or newlines)
- ✅ Use OAuth Playground/Graph Explorer for fresh tokens

**Solution:**
1. Generate a new refresh token
2. Update `GOOGLE_REFRESH_TOKEN` or `OUTLOOK_REFRESH_TOKEN` in Railway
3. Redeploy

---

### 3. Invalid Client ID/Secret

**Error Messages:**
- `Failed to initialize MSAL application`
- `Failed to create Gmail credentials from environment variables`

**Cause:** Client ID or secret is incorrect, or OAuth app is misconfigured.

**Prevention:**
- ✅ Verify credentials in Google Cloud Console / Azure Portal
- ✅ Ensure OAuth app type is correct (Desktop app for Google)
- ✅ Check redirect URIs are properly configured
- ✅ Verify API permissions are granted

**Solution:**
1. Double-check credentials in cloud console
2. Regenerate client secret if needed
3. Update environment variables in Railway
4. Redeploy

---

### 4. Insufficient API Scopes

**Error Messages:**
- `Failed to create Gmail service: Insufficient permissions`
- `Authentication failed: insufficient_scope`

**Cause:** Refresh token was obtained without required scopes.

**Prevention:**
- ✅ Request all required scopes when generating refresh token
- ✅ For Gmail: `gmail.readonly`, `gmail.modify`, `gmail.send`
- ✅ For Outlook: `Mail.Read`, `Mail.Send`, `Mail.ReadWrite`, `User.Read`, `offline_access`
- ✅ For Sheets: `spreadsheets`, `drive.file`, `drive`

**Solution:**
1. Generate new refresh token with all required scopes
2. Update refresh token in Railway
3. Redeploy

---

### 5. Invalid Service Account JSON

**Error Messages:**
- `Failed to parse SHEETS_SERVICE_ACCOUNT_JSON (invalid base64 or JSON)`
- `Service Account authentication failed`

**Cause:** Service account JSON is incorrectly base64-encoded or invalid.

**Prevention:**
- ✅ Verify base64 encoding is correct (no extra characters)
- ✅ Test base64 decoding locally: `echo $SHEETS_SERVICE_ACCOUNT_JSON | base64 -d | jq`
- ✅ Ensure service account has access to the spreadsheet
- ✅ Check JSON structure is valid

**Solution:**
1. Re-encode service account JSON: `cat service-account.json | base64`
2. Copy entire output (single line, no breaks)
3. Update `SHEETS_SERVICE_ACCOUNT_JSON` in Railway
4. Redeploy

---

## Runtime Errors

### 6. Port Configuration Issues

**Error Messages:**
- `Address already in use`
- `Port 8000 is already allocated`

**Cause:** Railway automatically sets `PORT` variable, but code might be hardcoded.

**Prevention:**
- ✅ Always use `os.getenv("PORT", default_port)` for port configuration
- ✅ Never hardcode port numbers in production code
- ✅ Use `PORT` environment variable from Railway

**Solution:**
- Code already handles this correctly:
  ```python
  PORT = int(os.getenv("PORT", 8000))  # Railway sets this automatically
  ```

---

### 7. Missing Dependencies

**Error Messages:**
- `ModuleNotFoundError: No module named 'xxx'`
- `ImportError: cannot import name 'xxx'`

**Cause:** Dependencies not installed or `requirements.txt` incomplete.

**Prevention:**
- ✅ Keep `requirements.txt` up to date
- ✅ Test `pip install -r requirements.txt` locally
- ✅ Railway auto-detects and installs from `requirements.txt`
- ✅ Pin dependency versions to avoid breaking changes

**Solution:**
1. Add missing package to `requirements.txt`
2. Commit and push to trigger Railway redeploy
3. Or manually trigger rebuild in Railway dashboard

---

### 8. File System Access Issues

**Error Messages:**
- `PermissionError: [Errno 13] Permission denied`
- `FileNotFoundError: [Errno 2] No such file or directory`

**Cause:** Railway's file system is ephemeral or read-only in some areas.

**Prevention:**
- ✅ Don't write token files (use environment variables)
- ✅ Use Railway volumes for persistent storage if needed
- ✅ Cache files in `/tmp` or project directory (temporary)
- ✅ All authentication now uses environment variables (fixed)

**Solution:**
- This is already resolved - no token files are used

---

### 9. Network/API Rate Limiting

**Error Messages:**
- `429 Too Many Requests`
- `rate_limit_exceeded`
- `Quota exceeded`

**Cause:** API rate limits exceeded for Google/Microsoft APIs.

**Prevention:**
- ✅ Implement exponential backoff (already in code)
- ✅ Add delays between API calls
- ✅ Use caching to reduce API calls
- ✅ Monitor API quota usage in cloud consoles

**Solution:**
- Code already handles rate limiting with retries
- Increase delays if issues persist
- Upgrade API quotas if needed

---

### 10. Database/Storage Access

**Error Messages:**
- `Connection refused`
- `Database does not exist`
- `Spreadsheet not found`

**Cause:** External services not accessible or credentials incorrect.

**Prevention:**
- ✅ Verify spreadsheet/service account permissions
- ✅ Check firewall/network settings
- ✅ Ensure service account has proper access
- ✅ Test connectivity before deploying

**Solution:**
1. Verify service account email has access to spreadsheet
2. Check API is enabled in Google Cloud Console
3. Verify network connectivity

---

## Configuration Errors

### 11. Incorrect MODE Setting

**Error Messages:**
- Server runs on wrong port
- Base URL incorrect

**Cause:** `MODE` environment variable not set or incorrect.

**Prevention:**
- ✅ Set `MODE=production` in Railway
- ✅ Keep `MODE=development` for local testing
- ✅ Verify port configuration matches MODE

**Solution:**
- Set `MODE=production` in Railway variables
- Redeploy

---

### 12. Missing API Keys

**Error Messages:**
- `GROQ_API_KEY is required`
- `Failed to initialize summarizer`

**Cause:** AI/LLM API key not set.

**Prevention:**
- ✅ Set `GROQ_API_KEY` in Railway
- ✅ Verify API key is valid and not expired
- ✅ Check API key has sufficient quota

**Solution:**
1. Obtain API key from Groq
2. Add `GROQ_API_KEY` to Railway variables
3. Redeploy

---

## Build/Deploy Errors

### 13. Python Version Mismatch

**Error Messages:**
- `SyntaxError: invalid syntax`
- `Python version X.X required`

**Cause:** Railway using wrong Python version.

**Prevention:**
- ✅ Add `runtime.txt` with Python version: `python-3.10.0`
- ✅ Or specify in `nixpacks.toml` or Railway settings
- ✅ Test locally with same Python version

**Solution:**
1. Create `runtime.txt`:
   ```
   python-3.10.0
   ```
2. Commit and redeploy

---

### 14. Build Timeout

**Error Messages:**
- `Build timeout exceeded`
- Deployment stuck at "Building"

**Cause:** Installation takes too long, or stuck dependency.

**Prevention:**
- ✅ Minimize dependencies in `requirements.txt`
- ✅ Use specific versions to avoid resolution delays
- ✅ Test build locally first
- ✅ Check for circular dependencies

**Solution:**
1. Review `requirements.txt` for unnecessary packages
2. Pin versions to specific releases
3. Retry deployment

---

### 15. Memory/Resource Limits

**Error Messages:**
- `Out of memory`
- `Process killed`
- Service crashes after deployment

**Cause:** Railway service exceeds memory limits.

**Prevention:**
- ✅ Monitor memory usage
- ✅ Upgrade Railway plan if needed
- ✅ Optimize code to reduce memory footprint
- ✅ Use caching wisely

**Solution:**
1. Check Railway metrics for memory usage
2. Upgrade to higher plan if needed
3. Optimize application code

---

## Verification Checklist

Before deploying to Railway:

- [ ] All required environment variables are set in Railway
- [ ] `.envSecrets` file exists locally for testing
- [ ] Refresh tokens are valid and include all required scopes
- [ ] Client IDs and secrets are correct
- [ ] Service account JSON is base64-encoded correctly
- [ ] `requirements.txt` includes all dependencies
- [ ] `MODE=production` is set in Railway
- [ ] `PORT` is not hardcoded (uses `os.getenv("PORT")`)
- [ ] No token files are referenced in code
- [ ] All authentication uses environment variables
- [ ] API keys are valid and have quota
- [ ] Spreadsheets/services are accessible
- [ ] Test locally before deploying

---

## Quick Debug Commands

**Check environment variables in Railway:**
```bash
# In Railway logs or console
env | grep -E "(GOOGLE|OUTLOOK|SHEETS|GROQ|MODE|PORT)"
```

**Test authentication locally:**
```python
from Gmail.gmail_auth import GmailAuth
from Outlook.outlook_auth import OutlookAuth

# Test Gmail
try:
    auth = GmailAuth()
    service = auth.authenticate()
    print("✅ Gmail auth successful")
except Exception as e:
    print(f"❌ Gmail auth failed: {e}")

# Test Outlook
try:
    auth = OutlookAuth()
    token = auth.get_access_token()
    print("✅ Outlook auth successful")
except Exception as e:
    print(f"❌ Outlook auth failed: {e}")
```

**Verify service account JSON:**
```bash
echo $SHEETS_SERVICE_ACCOUNT_JSON | base64 -d | jq .
```

---

## Support Resources

- **Google OAuth:** https://developers.google.com/identity/protocols/oauth2
- **Microsoft Graph:** https://docs.microsoft.com/en-us/graph/
- **Railway Docs:** https://docs.railway.app/
- **Project ENV_VARIABLES.md:** See this file for environment variable details


