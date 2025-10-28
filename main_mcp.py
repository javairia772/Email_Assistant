from fastmcp import FastMCP
# Import both connectors
from Outlook.outlook_connector import OutlookConnector
from Gmail.gmail_connector import GmailConnector

mcp = FastMCP(name="email_mcp_server")

# Initialize both clients
outlook = OutlookConnector()
gmail = GmailConnector()


# ----------------------------
# Gmail tools
# ----------------------------

@mcp.tool("gmail_list_threads")
def gmail_list_threads(max_results: int = 5):
    """List recent Gmail threads."""
    return gmail.list_threads(max_results)

@mcp.tool("gmail_get_message")
def gmail_get_message(thread_id: str):
    """Get a specific Gmail message thread."""
    return gmail.get_message(thread_id)

# ----------------------------
# Outlook tools
# ----------------------------

@mcp.tool(name="outlook_list_messages")
def outlook_list_messages(top: int = 5) -> list[dict]:
    """List latest Outlook messages."""
    return outlook.list_messages(top)

@mcp.tool(name="outlook_get_message")
def outlook_get_message(message_id: str) -> dict:
    """Fetch a specific Outlook message by ID."""
    return outlook.get_message(message_id)

# ----------------------------
# Run MCP
# ----------------------------
if __name__ == "__main__":
    mcp.run()  # STDIO or HTTP transport depending on Claude Desktop