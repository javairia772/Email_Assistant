import base64
import sys
import io
import os
import requests
from dotenv import load_dotenv
from Gmail.gmail_auth import GmailAuth
from Outlook.outlook_auth import OutlookAuth

# ✅ Fix Windows encoding issues (for MCP Inspector / Console)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

load_dotenv()


# ----------------------------- HELPER -----------------------------
def safe_text(text):
    """Ensure text is safely encoded to UTF-8."""
    if not text:
        return ""
    return text.encode("utf-8", "ignore").decode("utf-8", "ignore")


# ----------------------------- GMAIL UNREAD -----------------------------
def fetch_gmail_unread(limit=10):
    unread_emails = []
    try:
        service = GmailAuth().authenticate()
        results = service.users().messages().list(
            userId="me", q="is:unread", maxResults=limit
        ).execute()
        messages = results.get("messages", [])

        for msg in messages:
            message = service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in message["payload"]["headers"]}
            subject = safe_text(headers.get("Subject", "(No Subject)"))
            sender = safe_text(headers.get("From", "(Unknown Sender)"))
            date = safe_text(headers.get("Date", "Unknown Date"))
            snippet = safe_text(message.get("snippet", ""))

            # Decode plain text body
            body = ""
            parts = message["payload"].get("parts", [])
            for part in parts:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    try:
                        data = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8", errors="ignore"
                        )
                        body = safe_text(data)
                        break
                    except Exception:
                        pass

            unread_emails.append({
                "service": "Gmail",
                "from": sender,
                "subject": subject,
                "date": date,
                "snippet": snippet,
                "body": body,
            })

    except Exception as e:
        print(f"⚠️ Gmail fetch error: {e}")

    return unread_emails


# ----------------------------- OUTLOOK UNREAD -----------------------------
def fetch_outlook_unread(limit=10):
    unread_emails = []
    try:
        auth = OutlookAuth()
        token = auth.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.body-content-type="text"'}

        url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        params = {"$filter": "isRead eq false", "$top": limit}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json().get("value", [])
            for email in data:
                sender = safe_text(email.get("from", {}).get("emailAddress", {}).get("address", "(Unknown Sender)"))
                subject = safe_text(email.get("subject", "(No Subject)"))
                snippet = safe_text(email.get("bodyPreview", ""))
                date = safe_text(email.get("receivedDateTime", ""))
                body = safe_text(email.get("body", {}).get("content", ""))

                unread_emails.append({
                    "service": "Outlook",
                    "from": sender,
                    "subject": subject,
                    "date": date,
                    "snippet": snippet,
                    "body": body,
                })
        else:
            print(f"❌ Outlook fetch failed ({response.status_code}): {response.text}")

    except Exception as e:
        print(f"⚠️ Outlook fetch error: {e}")

    return unread_emails


# ----------------------------- COMBINED AGENT -----------------------------
def fetch_unread_emails(limit=10):
    """Fetch unread emails from both Gmail and Outlook."""
    gmail_data, outlook_data = [], []

    try:
        gmail_data = fetch_gmail_unread(limit)
    except Exception as e:
        print("⚠️ Gmail error:", e)

    try:
        outlook_data = fetch_outlook_unread(limit)
    except Exception as e:
        print("⚠️ Outlook error:", e)

    # Combine and print nicely for MCP Inspector
    all_emails = gmail_data + outlook_data
    print("📧 FETCHED UNREAD EMAILS\n-------------------------")
    for mail in all_emails:
        print(f"📨 Service: {mail['service']}")
        print(f"👤 From: {mail['from']}")
        print(f"📅 Date: {mail['date']}")
        print(f"📌 Subject: {mail['subject']}")
        print(f"📝 Snippet: {mail['snippet']}")
        print(f"📄 Body:\n{mail['body']}")
        print("-" * 60)

    return {"gmail": gmail_data, "outlook": outlook_data}


# ----------------------------- TEST STANDALONE -----------------------------
if __name__ == "__main__":
    fetch_unread_emails(limit=5)
