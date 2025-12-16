#\!/usr/bin/env python3
"""
SWAT Team MCP Client Example
This shows how to connect to your email MCP server and send assignment emails
"""

from fastmcp import FastMCP

def send_assignment_email():
    # Connect to your MCP server via ngrok
    mcp = FastMCP(url="https://your-mcp-ngrok-link.ngrok-free.dev")
    
    # Assignment data
    assignment_data = {
        "Student_Email": "ali@example.com",
        "Student_Name": "Ali",
        "TaskDescription": "Analyze dataset and create visualization report",
        "Supervisor_Name": "Dr. X",
        "Supervisor_Email": "drx@example.com",
        "Document": "https://docs.google.com/document/d/12345",
        "Deadline": "2025-12-20"
    }
    
    # Call the MCP tool
    result = mcp.call("SendEmail", assignment_data)
    
    print("MCP Tool Result:")
    print(result)
    return result

if __name__ == "__main__":
    send_assignment_email()
