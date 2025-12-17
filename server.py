# server.py
import os
import traceback
from dotenv import load_dotenv
import re

# Load environment variables from .env file
load_dotenv('.envSecrets')

from fastmcp import FastMCP
from fastapi import FastAPI

# Create FastAPI app
app = FastAPI()

# Initialize MCP with the app
mcp = FastMCP(name="email_mcp_server")
app.mount("/mcp", mcp)
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Agents.contact_aggregator_agent import ContactAggregatorAgent
from Agents.email_agent import EmailAgent
from Agents.agent_tools import AgentTools
from Summarizer.groq_summarizer import GroqSummarizer
from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic
from classifier.email_classifier import classify_email
from integrations.google_sheets import upsert_summaries
from providers.sent_store import SentStore
from datetime import datetime


# Initialize MCP and connectors
gmail = GmailConnector()
outlook = OutlookConnector()
summarizer = GroqSummarizer()  # this uses the cache built into the class
agent = EmailAgent()
agent_tools = AgentTools()
sent_store = SentStore()

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
# Basic email fetch tools
# (these are thin wrappers over your connectors)
# --------------------
@mcp.tool("gmail_list_threads")
def m_gmail_list_threads(max_results: int = 5):
    return safe_run(gmail.list_threads, max_results)

@mcp.tool("gmail_fetch_threads_by_contact")
def m_gmail_fetch_threads(contact_email: str, max_results: int = 50):
    """
    Returns: list of threads, where each thread is list[message_dict].
    """
    return safe_run(gmail.fetch_threads, contact_email, max_results)

@mcp.tool("gmail_get_thread_text")
def m_gmail_get_thread_text(thread_id: str):
    return safe_run(gmail.get_thread_text, thread_id)

@mcp.tool("outlook_list_messages")
def m_outlook_list_messages(top: int = 5):
    return safe_run(outlook.list_messages, top)

@mcp.tool("outlook_fetch_threads_by_contact")
def m_outlook_fetch_threads(contact_email: str, top: int = 50):
    return safe_run(outlook.fetch_threads, contact_email, top)

@mcp.tool("outlook_get_thread_text")
def m_outlook_get_thread_text(message_id: str):
    return safe_run(outlook.get_thread_text, message_id)


def _build_agent_email_payload(source: str, thread_id: str):
    source = source.lower()
    try:
        if source == "gmail":
            thread_messages = gmail.fetch_threads_by_id(thread_id)
            if isinstance(thread_messages, dict) and thread_messages.get("error"):
                return {"error": thread_messages.get("error")}
            if not thread_messages:
                return {"error": "Thread not found"}
            latest = thread_messages[-1]
            combined = "\n\n---\n\n".join(
                f"From: {msg.get('sender','Unknown')}\nSubject: {msg.get('subject','')}\n\n{msg.get('body','')}"
                for msg in thread_messages
            )
            sender = latest.get("sender", "unknown")
            subject = latest.get("subject", "(no subject)")
            classification = classify_email(
                latest.get("sender", sender),
                latest.get("subject", subject),
                latest.get("body", combined)
            )
            return {
                "id": thread_id,
                "source": "gmail",
                "sender": sender,
                "subject": subject,
                "body": combined,
                "importance": classification.get("importance", "Unknown"),
                "role": classification.get("role", "Unknown"),
            }
        elif source == "outlook":
            message = outlook.get_message(thread_id)
            sender = message.get("sender", "unknown")
            subject = message.get("subject", "(no subject)")
            body = message.get("body", "")
            classification = classify_email(sender, subject, body)
            return {
                "id": thread_id,
                "source": "outlook",
                "sender": sender,
                "subject": subject,
                "body": body,
                "importance": classification.get("importance", "Unknown"),
                "role": classification.get("role", "Unknown"),
            }
        else:
            return {"error": "Unknown source. Use 'gmail' or 'outlook'."}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool("agent_process_email")
def m_agent_process_email(source: str, thread_id: str):
    """
    Run the autonomous EmailAgent on a given thread.
    """
    payload = _build_agent_email_payload(source, thread_id)
    if payload.get("error"):
        return {"ok": False, "error": payload["error"]}

    result = agent.process_email(payload, agent_tools.get_all_tools())
    return {"ok": True, "result": result}



# --------------------
# Summarization helpers (TTL + per-contact caching)
# --------------------
# def summarize_thread_logic(source: str, contact_email: str, thread_id: str, thread_obj=None, force=False):
#     """
#     Summarizes a single thread automatically.
#     - Per-contact caching namespace
#     - TTL-aware caching
#     - force=True clears all cached threads for this contact
#     """
#     try:
#         if force:
#             summarizer._clear_contact_cache(source, contact_email)

#         cached_summary = summarizer._get_from_cache(source, contact_email, thread_id)
#         if cached_summary:
#             print(f"⚡ Using cached summary for {contact_email}:{thread_id}")
#             return {
#                 "thread_id": thread_id,
#                 "summary": cached_summary,
#                 "used_cache": True
#             }

#         # Normalize thread_obj
#         if thread_obj is None:
#             if source.lower() == "gmail":
#                 thread_obj = gmail.get_thread_text(thread_id)
#             elif source.lower() == "outlook":
#                 thread_obj = outlook.get_thread_text(thread_id)
#             else:
#                 raise ValueError(f"Unknown source: {source}")

#         if isinstance(thread_obj, str):
#             thread_obj = [{"sender": "Unknown", "subject": "No Subject", "body": thread_obj}]
#         elif not isinstance(thread_obj, list):
#             thread_obj = [thread_obj]


#         # Combine messages
#         combined = "\n\n---\n\n".join(
#             f"From: {m.get('sender','Unknown')}\nSubject: {m.get('subject','No Subject')}\n\n{m.get('body','')}"
#             for m in thread_obj
#         )

#         # Generate summary
#         summary = summarizer.summarize_text(combined)

#         # Save in cache
#         summarizer._set_cache(source, contact_email, thread_id, summary)

#         return {
#             "thread_id": thread_id,
#             "summary": summary,
#             "used_cache": False
#         }

#     except Exception as e:
#         return {"error": str(e), "traceback": traceback.format_exc()}


# def summarize_contact_logic(source: str, contact_email: str, top: int = 50, force_refresh: bool = False):
#     """
#     Summarizes all threads for a contact.
#     - TTL-aware per-thread caching
#     - force_refresh clears the contact's cache if True
#     """
#     try:
#         # Fetch threads
#         if source.lower() == "outlook":
#             fetch_res = outlook.fetch_threads(contact_email, top)
#         else:
#             fetch_res = gmail.fetch_threads(contact_email, top)

#         if isinstance(fetch_res, dict) and fetch_res.get("error"):
#             return {"error": fetch_res}

#         threads = fetch_res or []
#         thread_summaries = []

#         for i, thread in enumerate(threads, start=1):
#             thread_id = thread[0].get("conversationId") or thread[0].get("threadId") or f"{source}_thread_{i}"

#             s = summarize_thread_logic(source, contact_email, thread_id, thread_obj=thread, force=force_refresh)
#             if s.get("error"):
#                 thread_summaries.append({"thread_id": thread_id, "error": s["error"]})
#             else:
#                 thread_summaries.append({
#                     "thread_id": thread_id,
#                     "summary": s["summary"],
#                     "used_cache": s.get("used_cache", False)
#                 })

#         summaries_texts = [t["summary"] for t in thread_summaries if "summary" in t]
#         contact_summary = summarizer.summarize_contact_threads(
#             summaries_texts, source=source, contact_email=contact_email, force=force_refresh
#         ) if summaries_texts else ""

#         return {    
#             "contact_email": contact_email,
#             "source": source,
#             "thread_count": len(threads),
#             "thread_summaries": thread_summaries,
#             "contact_summary": contact_summary,
#             "display_summary": contact_summary
#         }

#     except Exception as e:
#         return {"error": str(e), "traceback": traceback.format_exc()}


# --------------------
# Summarization tools (MCP registered)
# --------------------
# @mcp.tool("summarize_thread")
# def m_summarize_thread(source: str, thread_index_or_id, force: bool = False):
#     """
#     MCP tool that automatically fetches and summarizes an email thread.
#     """
#     try:
#         source = source.lower()

#         # ✅ Auto-fetch structured thread data properly
#         if source == "gmail":
#             fetch_fn = getattr(gmail, "fetch_threads_by_id", gmail.get_thread_text)
#         elif source == "outlook":
#             fetch_fn = getattr(outlook, "fetch_threads_by_conversation", outlook.get_thread_text)
#         else:
#             raise ValueError("Unknown source. Use 'gmail' or 'outlook'.")

#         thread_obj = fetch_fn(thread_index_or_id)


#         # ✅ Normalize structure to always be a list of dicts
#         if isinstance(thread_obj, str):
#             thread_obj = [{"sender": "Unknown", "subject": "No Subject", "body": thread_obj}]
#         elif not isinstance(thread_obj, list):
#             thread_obj = [thread_obj]

#         return summarize_thread_logic(source, thread_index_or_id, thread_obj=thread_obj, force=force)

#     except Exception as e:
#         return {"error": str(e), "traceback": traceback.format_exc()}




# @mcp.tool("summarize_thread")
# def m_summarize_thread(source: str, contact_email: str, thread_id: str, force: bool = False):
#     """
#     Summarizes a single thread for a contact.
#     """
#     return summarize_thread_logic(source, contact_email, thread_id, force=force)


@mcp.tool("summarize_contact")
def m_summarize_contact(source: str, contact_email: str, top: int = 50, force_refresh: bool = False):
    if source.lower() == "outlook":
        fetch_fn = outlook.fetch_threads
    else:
        fetch_fn = gmail.fetch_threads

    full_result = summarize_contact_logic(source, contact_email, fetch_fn, top, force_refresh)

    # 🟢 Save result to Google Sheets
    if full_result and full_result.get("contact_summary"):
        row = [{
            "id": contact_email,
            "email": contact_email,
            "role": "Unknown",
            "summary": full_result["contact_summary"],
            "date": datetime.utcnow().isoformat()
        }]
        upsert_summaries("EmailAssistantSummaries", row)

    return {
        "contact_email": full_result.get("contact_email"),
        "source": full_result.get("source"),
        "contact_summary": full_result.get("contact_summary")
    }



# --------------------
# Cache management tools
# --------------------
@mcp.tool("list_cached_summaries")
def m_list_cached_summaries():
    summarizer._cleanup_expired_cache()
    return {"keys": list(summarizer.cache.keys()), "count": len(summarizer.cache)}


@mcp.tool("clear_cache")
def m_clear_cache(force: bool = False):
    """
    Clears cache entries.
    - force=True: clears all contacts
    - force=False: clears only expired entries
    """
    if force:
        summarizer.cache = {}
    else:
        summarizer._cleanup_expired_cache()
    summarizer._save_cache()
    return {"ok": True, "remaining_keys": list(summarizer.cache.keys())}


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