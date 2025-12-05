# 📧 Email Assistant System

## 🧠 Overview

The **Email Assistant System** is a unified **MCP-based assistant** that helps **Lab Directors** efficiently manage their email inboxes from both **Gmail** and **Outlook**.  

It automates key workflows such as:
- Fetching and parsing incoming emails  
- Summarizing long threads intelligently  
- Generating and sending replies automatically  
- Scheduling follow-up tasks and reminders  

Powered by:
- ⚙️ **FastMCP** for modular coordination  
- 🧠 **GROQ** for efficient inference  
- 📬 **Google & Microsoft APIs** for secure email integration

### External MCP integration (agentic send-email)
- Use `connectors/mcp_send_email_tool.py` in a separate MCP server to expose a `send_email_via_mcp` tool.
- Other projects can call that MCP tool with `to`, `subject`, `body`, optional `attachments`, and `source` (gmail|outlook) to trigger delivery via this service.