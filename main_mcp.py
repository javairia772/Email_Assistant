from fastmcp import FastMCP
from Agents.contact_aggregator_agent import ContactAggregatorAgent
from connectors.gmail_connector import list_threads, get_message as get_gmail_message
import asyncio
import json

# Initialize MCP server
mcp = FastMCP(name="email_mcp_server")

# ----------------------------
# Gmail tools
# ----------------------------
@mcp.tool()
async def gmail_list_threads(max_results: int = 5):
    """List Gmail threads"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, list_threads, max_results)

@mcp.tool()
async def gmail_get_thread(thread_id: str):
    """Get a specific Gmail thread"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_gmail_message, thread_id)

# ----------------------------
# Contact Aggregator Tool
# ----------------------------
def process_contacts_sync(max_threads: int = 5):
    contact_agent = ContactAggregatorAgent()
    threads = list_threads(max_results=max_threads)  # sync call

    for t in threads:
        thread_id = t.get("id")
        if thread_id:
            thread_obj = get_gmail_message(thread_id)  # sync call
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
@mcp.tool()
async def gmail_fetch_unread_emails(max_results: int = 5):
    """
    Fetch latest unread Gmail emails (sender, subject, snippet).
    """
    from connectors.gmail_connector import get_gmail_service  # ensure service helper exists
    import base64
    from email import message_from_bytes

    def fetch_emails():
        service = get_gmail_service()
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
