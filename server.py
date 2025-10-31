# server.py
import os
import traceback
from fastmcp import FastMCP
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Summarizer.groq_summarizer import GroqSummarizer
from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic

# Initialize MCP and connectors
mcp = FastMCP(name="email_mcp_server")
gmail = GmailConnector()
outlook = OutlookConnector()
summarizer = GroqSummarizer()  # this uses the cache built into the class

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
    """
    Summarizes all threads for a contact.
    - force_refresh=True clears the contact cache before summarizing
    """
    if source.lower() == "outlook":
        fetch_fn = outlook.fetch_threads
    else:
        fetch_fn = gmail.fetch_threads

    full_result = summarize_contact_logic(source, contact_email, fetch_fn, top, force_refresh)

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



# --------------------
# Run MCP
# --------------------
if __name__ == "__main__":
    mcp.cache_contact_summary = {}
    mcp.run()
