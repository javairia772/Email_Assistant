from fastmcp import FastMCP
from connectors.gmail_connector import list_threads, get_message as get_gmail_message
import asyncio

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
# Run MCP
# ----------------------------
if __name__ == "__main__":
    mcp.run()  # STDIO or HTTP transport depending on Claude Desktop
