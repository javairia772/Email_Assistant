"""
Lightweight MCP tool module to allow external agentic systems
to trigger outbound email via this project.

Expose the function `send_email_via_mcp(to, subject, body, source="gmail", attachments=None)`
and wire it in a separate MCP server (not the main one) so other
projects can call it through Model Context Protocol.
"""
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector


def send_email_via_mcp(to: str, subject: str, body: str, source: str = "gmail", attachments=None) -> dict:
    attachments = attachments or []
    src = (source or "gmail").lower()
    if src == "gmail":
        GmailConnector().send_email(to, subject, body, attachments)
    elif src == "outlook":
        OutlookConnector().send_email(to, subject, body, attachments)
    else:
        raise ValueError("Unsupported source (expected gmail|outlook)")
    return {"ok": True, "to": to, "subject": subject, "source": src}

