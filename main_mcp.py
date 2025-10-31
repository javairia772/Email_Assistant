from fastmcp import FastMCP
from Agents.contact_aggregator_agent import ContactAggregatorAgent
from Outlook.outlook_connector import OutlookConnector
from Gmail.gmail_connector import GmailConnector
import json

# Initialize MCP server
mcp = FastMCP(name="email_mcp_server")

# Initialize both clients
outlook = OutlookConnector()
gmail = GmailConnector()


# ----------------------------
# Raw helper functions used by provider and tools
# ----------------------------

def gmail_list_threads_raw(max_results: int = 5):
    return gmail.list_threads(max_results)

def gmail_get_message_raw(thread_id: str):
    return gmail.get_message(thread_id)

def outlook_list_messages_raw(top: int = 5) -> list[dict]:
    return outlook.list_messages(top)

# ----------------------------
# MCP tools - list endpoints
# ----------------------------

@mcp.tool("gmail_list_threads")
def gmail_list_threads(max_results: int = 5):
    return gmail_list_threads_raw(max_results)

@mcp.tool("gmail_get_message")
def gmail_get_message(thread_id: str):
    return gmail_get_message_raw(thread_id)

@mcp.tool(name="outlook_list_messages")
def outlook_list_messages(top: int = 5) -> list[dict]:
    return outlook_list_messages_raw(top)


# ----------------------------
# Agentic tool: aggregate contacts across sources
# ----------------------------

@mcp.tool(name="agent_aggregate_contacts")
def agent_aggregate_contacts(max_threads: int = 50, include_outlook: bool = True, unread_only: bool = False):
    """
    Aggregate contacts using ContactAggregatorAgent from latest Gmail threads
    (and optionally Outlook messages). If unread_only is True, only consider
    unread Gmail messages.
    """
    import base64
    from datetime import datetime, timezone

    contact_agent = ContactAggregatorAgent()

    # --- Gmail: latest threads or unread ---
    try:
        if unread_only:
            # Use raw Gmail service to list unread for precision
            service = gmail.auth.authenticate()
            results = service.users().messages().list(
                userId="me",
                labelIds=["INBOX", "UNREAD"],
                maxResults=max_threads,
            ).execute()
            messages = results.get("messages", [])
            for m in messages:
                tid = m.get("id")
                if not tid:
                    continue
                # get full thread structure via connector for agent compatibility
                thread = gmail.get_message(tid)
                contact_agent.process_email(thread)
        else:
            gmail_threads = gmail.list_threads(max_results=max_threads)
            for t in gmail_threads:
                tid = t.get("id")
                if not tid:
                    continue
                thread = gmail.get_message(tid)
                contact_agent.process_email(thread)
    except Exception as e:
        print(f"[AgentAggregate] Gmail error: {e}")

    # --- Outlook (optional): adapt message to Gmail-like thread for agent ---
    if include_outlook:
        try:
            msgs = outlook.list_messages(top=max_threads)
            for msg in msgs:
                # Build fake Gmail-like thread object
                # Convert ISO 8601 to RFC 2822-like without TZ suffix for agent parser
                try:
                    iso = msg.get("receivedDateTime", "")
                    if iso:
                        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
                        rfc = dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S")
                    else:
                        rfc = ""
                except Exception:
                    rfc = ""
                headers = [
                    {"name": "From", "value": msg.get("from", "")},
                    {"name": "To", "value": ""},
                    {"name": "Cc", "value": ""},
                    {"name": "Date", "value": rfc},
                ]
                thread_like = {
                    "id": msg.get("id"),
                    "messages": [
                        {
                            "payload": {
                                "headers": headers
                            }
                        }
                    ]
                }
                contact_agent.process_email(thread_like)
        except Exception as e:
            print(f"[AgentAggregate] Outlook error: {e}")

    # Emit per-contact summary
    return [
        {
            "name": info.get("name"),
            "email": email,
            "threads": info.get("emails"),
            "last_contacted": str(info.get("last_contacted"))
        }
        for email, info in contact_agent.get_contacts().items()
    ]


# ----------------------------
# Run MCP
# ----------------------------
if __name__ == "__main__":
    mcp.run()
