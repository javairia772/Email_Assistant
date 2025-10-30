from fastmcp import FastMCP
from Agents.contact_aggregator_agent import ContactAggregatorAgent
from Outlook.outlook_connector import OutlookConnector
from Gmail.gmail_connector import GmailConnector
import asyncio
import json

# Initialize MCP server
mcp = FastMCP(name="email_mcp_server")

# Initialize both clients
outlook = OutlookConnector()
gmail = GmailConnector()


# ----------------------------
# Gmail tools
# ----------------------------

def gmail_list_threads_raw(max_results: int = 5):
    """Plain helper: List recent Gmail threads (not wrapped)."""
    return gmail.list_threads(max_results)

@mcp.tool("gmail_list_threads")
def gmail_list_threads(max_results: int = 5):
    """List recent Gmail threads."""
    return gmail_list_threads_raw(max_results)

def gmail_get_message_raw(thread_id: str):
    """Plain helper: Get a specific Gmail message thread (not wrapped)."""
    return gmail.get_message(thread_id)

@mcp.tool("gmail_get_message")
def gmail_get_message(thread_id: str):
    """Get a specific Gmail message thread."""
    return gmail_get_message_raw(thread_id)

# ----------------------------
# Outlook tools
# ----------------------------

def outlook_list_messages_raw(top: int = 5) -> list[dict]:
    """Plain helper: List latest Outlook messages (not wrapped)."""
    return outlook.list_messages(top)

@mcp.tool(name="outlook_list_messages")
def outlook_list_messages(top: int = 5) -> list[dict]:
    """List latest Outlook messages."""
    return outlook_list_messages_raw(top)

def outlook_get_message_raw(message_id: str) -> dict:
    """Plain helper: Fetch a specific Outlook message by ID (not wrapped)."""
    return outlook.get_message(message_id)

@mcp.tool(name="outlook_get_message")
def outlook_get_message(message_id: str) -> dict:
    """Fetch a specific Outlook message by ID."""
    return outlook_get_message_raw(message_id)

# ----------------------------
# Contact Aggregator Tool
# ----------------------------
def process_contacts_sync(max_threads: int = 5):
    contact_agent = ContactAggregatorAgent()
    threads = gmail.list_threads(max_results=max_threads)  # sync call

    for t in threads:
        thread_id = t.get("id")
        if thread_id:
            thread_obj = gmail.get_message(thread_id)  # sync call
            contact_agent.process_email(thread_obj)

    contacts = contact_agent.get_contacts()
    
    # Save JSON
    with open("contacts.json", "w") as f:
        json.dump(
            {
                k: {
                    "name": v["name"],
                    "emails": v["emails"],
                    "last_contacted": str(v["last_contacted"])
                } 
                for k, v in contacts.items()
            },
            f,
            indent=4
        )
    return contacts
@mcp.tool()
async def extract_unique_contacts(max_threads: int = 5):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, process_contacts_sync, max_threads)


# ----------------------------
# Gmail Fetch Unread Emails Tool
# ----------------------------
@mcp.tool()
async def gmail_fetch_unread_emails(max_results: int = 5):
    """
    Fetch latest unread Gmail emails (sender, subject, snippet).
    """
    import base64
    from email import message_from_bytes

    def fetch_emails():
        # Reuse existing GmailConnector instance to get the authenticated service
        service = gmail.auth.authenticate()
        results = service.users().messages().list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results).execute()
        messages = results.get("messages", [])
        emails = []

        for msg in messages:
            msg_detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
            payload = msg_detail.get("payload", {})
            headers = payload.get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "(Unknown Sender)")
            snippet = msg_detail.get("snippet", "")

            # Extract body (optional)
            body = ""
            parts = payload.get("parts", [])
            if parts:
                data = parts[0].get("body", {}).get("data")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

            emails.append({
                "id": msg["id"],
                "from": sender,
                "subject": subject,
                "snippet": snippet,
                "body": body[:300] + "..." if body else snippet
            })

        return emails

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_emails)


# ----------------------------
# Run MCP
# ----------------------------
if __name__ == "__main__":
    mcp.run()
