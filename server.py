# server.py
#import os
from fastmcp import FastMCP
from fastapi import FastAPI
import traceback
from dotenv import load_dotenv
import re

# Load environment variables from .env file
load_dotenv('.env')


# Create FastAPI app
app = FastAPI()

# Initialize MCP with the app
mcp = FastMCP(name="email_mcp_server")
app.mount("/mcp", mcp)
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Summarizer.groq_summarizer import GroqSummarizer
from Summarizer.summarize_helper import  summarize_contact_logic , summarize_thread_logic 
from classifier.email_classifier import classify_email
from integrations.google_sheets import upsert_summaries
from integrations.google_calendar import GoogleCalendar
from providers.sent_store import SentStore
from datetime import datetime
import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize MCP and connectors
gmail = GmailConnector()
outlook = OutlookConnector()
summarizer = GroqSummarizer()  
sent_store = SentStore()

# Initialize Google Calendar integration
try:
    calendar = GoogleCalendar(credentials_path='credentials.json')
    logger.info("Google Calendar integration initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Google Calendar: {str(e)}")
    calendar = None

# --------------------
# Utilities
# --------------------
def safe_run(fn, *args, **kwargs):
    """Helper to run and return structured error on exception."""
    try:
        return {"ok": True, "result": fn(*args, **kwargs)}
    except Exception as e:
        tb = traceback.format_exc()
        return {"ok": False, "error": str(e), "traceback": tb}

# --------------------
# MCP Email Sending for Assignment Emails
# --------------------

EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")

def validate_email(email: str) -> bool:
    """Simple email format validation"""
    return bool(email and EMAIL_REGEX.fullmatch(email.strip()))

def sendReplyFromMCP(mcp_data: dict):
    """
    Process MCP data and send an assignment email to a student.
    Includes validations for required fields and email formats.
    """
    try:
        # Extract MCP data with defaults
        student_email = mcp_data.get("Student_Email", "").strip()
        student_name = mcp_data.get("Student_Name", "").strip()
        task_description = mcp_data.get("TaskDescription", "").strip()
        supervisor_name = mcp_data.get("Supervisor_Name", "").strip()
        supervisor_email = mcp_data.get("Supervisor_Email", "").strip()
        researcher_name = mcp_data.get("Researcher_Name", "").strip()
        researcher_email = mcp_data.get("Researcher_Email", "").strip()

        # Validate required fields
        if not student_email:
            return {"ok": False, "error": "Student_Email is required"}
        if not validate_email(student_email):
            return {"ok": False, "error": "Student_Email is invalid"}

        if not task_description:
            return {"ok": False, "error": "TaskDescription is required"}
        if not isinstance(task_description, str):
            return {"ok": False, "error": "TaskDescription must be a string"}

        if supervisor_email and not validate_email(supervisor_email):
            return {"ok": False, "error": "Supervisor_Email is invalid"}

        if researcher_email and not validate_email(researcher_email):
            return {"ok": False, "error": "Researcher_Email is invalid"}

        if student_name and not isinstance(student_name, str):
            return {"ok": False, "error": "Student_Name must be a string"}
        if supervisor_name and not isinstance(supervisor_name, str):
            return {"ok": False, "error": "Supervisor_Name must be a string"}
        if researcher_name and not isinstance(researcher_name, str):
            return {"ok": False, "error": "Researcher_Name must be a string"}

        # Build email subject
        subject = f"Assignment: {task_description[:50]}{'...' if len(task_description) > 50 else ''}"

        # Build email body
        body_lines = [
            f"Dear {student_name if student_name else 'Student'},",
            "",
            "I hope this email finds you well. You have been assigned the following task:",
            "",
            f"Task Description:\n{task_description}",
            ""
        ]

        # Add researcher info
        if researcher_name or researcher_email:
            body_lines.append("For guidance or questions, you may contact the researcher:")
            if researcher_name:
                body_lines.append(f"Researcher Name: {researcher_name}")
            if researcher_email:
                body_lines.append(f"Researcher Email: {researcher_email}")
            body_lines.append("")

        # Add supervisor info
        if supervisor_name or supervisor_email:
            body_lines.append("For any additional questions or clarifications, please contact the supervisor:")
            if supervisor_name:
                body_lines.append(f"Supervisor Name: {supervisor_name}")
            if supervisor_email:
                body_lines.append(f"Supervisor Email: {supervisor_email}")
            body_lines.append("")

        # Closing
        body_lines.append("Please acknowledge receipt of this assignment and confirm your understanding.")
        body_lines.append("")
        body_lines.append("Best regards,")

        body = "\n".join(body_lines)

        # Send email using existing infrastructure (Gmail first, Outlook fallback)
        try:
            gmail.send_email(student_email, subject, body, attachments=None)
            sent_store.record(student_email, subject, body, source="gmail")
            return {"ok": True, "to": student_email, "subject": subject}
        except Exception as email_error:
            try:
                outlook.send_email(student_email, subject, body, attachments=None)
                sent_store.record(student_email, subject, body, source="outlook")
                return {"ok": True, "to": student_email, "subject": subject}
            except Exception:
                return {"ok": False, "error": f"Failed to send email: {str(email_error)}"}

    except Exception as e:
        return {"ok": False, "error": f"Error processing MCP data: {str(e)}"}


@mcp.tool("SendEmailJSON")
def m_send_email_json(
    student_email: str,
    student_name: str,
    task_description: str,
    supervisor_name: str = "",
    supervisor_email: str = "",
    researcher_name: str = "",
    researcher_email: str = ""
) -> dict:
    """
    Send an assignment email to a student with task details.
    Validates required fields and email formats.
      Args:
        student_email: Email address of the student
        student_name: Name of the student
        task_description: Description of the assignment task
        supervisor_name: Name of the supervisor
        supervisor_email: Email of the supervisor
        document: Optional document attachment
        deadline: Optional deadline for the task
    """
    mcp_data = {
        "Student_Email": student_email.strip(),
        "Student_Name": student_name.strip(),
        "TaskDescription": task_description.strip(),
        "Supervisor_Name": supervisor_name.strip(),
        "Supervisor_Email": supervisor_email.strip(),
        "Researcher_Name": researcher_name.strip(),
        "Researcher_Email": researcher_email.strip(),
    }

    return sendReplyFromMCP(mcp_data)


# --------------------
# Run MCP Server
# --------------------
if __name__ == "__main__":

    mcp.cache_contact_summary = {}
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8001,
    )