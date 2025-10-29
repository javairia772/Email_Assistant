from fastmcp import FastMCP
from Agents.contact_aggregator_agent import ContactAggregatorAgent
from connectors.gmail_connector import list_threads, get_message as get_gmail_message
import asyncio
import json
import threading
import time

# Initialize MCP server
mcp = FastMCP(name="email_mcp_server")
mcp.resources = {}  # simple cache to hold latest contact data for MCP UI

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
# Contact Aggregator Agent (emoji-free)
# ----------------------------
file_lock = threading.Lock()  # ensures thread-safe file writes

def log_refresh(message):
    """Simple local log for background contact updates."""
    with open("refresh_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

def process_contacts_sync(max_threads: int = 5):
    print(f"[DEBUG] process_contacts_sync ran at {time.strftime('%H:%M:%S')}")

    contact_agent = ContactAggregatorAgent()
    threads = list_threads(max_results=max_threads)

    for t in threads:
        thread_id = t.get("id")
        if thread_id:
            thread_obj = get_gmail_message(thread_id)
            contact_agent.process_email(thread_obj)

    contacts = contact_agent.get_contacts()

    with file_lock:
        with open("contacts.json", "w", encoding="utf-8") as f:
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
                indent=4,
                ensure_ascii=False
            )

    msg = f"Contacts updated. ({len(contacts)} total)"
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    log_refresh(msg)
    return contacts


@mcp.tool()
async def extract_unique_contacts(max_threads: int = 5):
    """Manual trigger for contact extraction"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, process_contacts_sync, max_threads)


# ----------------------------
# Background Auto Refresh (Thread-Based)
# ----------------------------
def auto_refresh_contacts(interval_minutes=10):  # 1 min for testing
    """Runs in a separate thread, refreshing contacts every N minutes."""
    while True:
        print(f"[Scheduler] Running contact aggregation at {time.strftime('%H:%M:%S')}...")
        try:
            contacts = process_contacts_sync()

            # ✅ Convert any datetime objects to strings for JSON safety
            safe_contacts = {}
            for k, v in contacts.items():
                safe_contacts[k] = {
                    "name": v["name"],
                    "emails": v["emails"],
                    "last_contacted": (
                        v["last_contacted"].strftime("%Y-%m-%d %H:%M:%S")
                        if hasattr(v["last_contacted"], "strftime")
                        else v["last_contacted"]
                    ),
                }

            # ✅ Update MCP internal cache
            mcp.resources["contacts"] = safe_contacts

            # ✅ Notify MCP dashboard (forces UI refresh)
            try:
                pass  # or remove the line entirely

                print("[MCP] UI resource 'contacts' updated successfully.")
            except Exception as e:
                print(f"[MCP Warning] UI resource not refreshed: {e}")

            # ✅ Save to JSON
            with open("contact.json", "w", encoding="utf-8") as f:
                json.dump(safe_contacts, f, indent=4, ensure_ascii=False)

            log_refresh("Contacts successfully updated.")
            print("[Scheduler] Completed contact refresh.\n")

        except Exception as e:
            log_refresh(f"Scheduler Error: {e}")
            print(f"[Scheduler Error] {e}. Retrying in 1 minute...")

        time.sleep(interval_minutes * 60)

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
    print(f"[MCP] Email Assistant started successfully at {time.strftime('%H:%M:%S')}")
    threading.Thread(target=auto_refresh_contacts, daemon=True).start()
    mcp.run()
