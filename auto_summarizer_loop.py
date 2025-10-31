# auto_summarizer_loop.py
import os
import time
import json
from datetime import datetime, timezone
from collections import defaultdict
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic
from server import mcp  # MCP instance

# -----------------------------
# Cache file
# -----------------------------
SUMMARY_CACHE = "Summaries/summary_cache.json"

# -----------------------------
# Cache helpers
# -----------------------------
def load_cache():
    os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)
    if not os.path.exists(SUMMARY_CACHE):
        return {"seen": {"gmail": set(), "outlook": set()}, "summaries": {}}

    with open(SUMMARY_CACHE, "r", encoding="utf-8") as f:
        data = json.load(f)
        data["seen"]["gmail"] = set(data["seen"].get("gmail", []))
        data["seen"]["outlook"] = set(data["seen"].get("outlook", []))
        return data


def save_cache(cache):
    data = {
        "seen": {
            "gmail": list(cache["seen"]["gmail"]),
            "outlook": list(cache["seen"]["outlook"]),
        },
        "summaries": cache["summaries"],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    with open(SUMMARY_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -----------------------------
# Helper: exponential backoff for rate-limited Groq calls
# -----------------------------
def safe_summarize_thread(source, contact_email, thread_id, thread_obj=None, max_retries=5):
    delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            return summarize_thread_logic(source, contact_email, thread_id, thread_obj=thread_obj, force=False)
        except Exception as e:
            msg = str(e)
            if "rate_limit" in msg.lower() or "429" in msg:
                print(f"⚠️ Groq rate limit hit for {thread_id}, retrying in {delay}s (attempt {attempt})")
                time.sleep(delay)
                delay *= 2  # exponential backoff
            else:
                print(f"[ERROR] Failed summarizing thread {thread_id}: {msg}")
                return {"error": msg}
    return {"error": f"Max retries exceeded for {thread_id}"}


# -----------------------------
# Summarize a batch of threads/emails
# -----------------------------
def summarize_platform(source, connector, cache, list_fn, fetch_fn, id_key="id"):
    print(f"\n🔍 Checking {source.title()} for new emails...")

    seen = cache["seen"][source]
    summaries = cache["summaries"]
    new_count = 0

    try:
        threads = list_fn()
        contact_threads = defaultdict(list)

        # Group messages by sender/contact
        for item in threads:
            email_id = item.get(id_key) or item.get("threadId") or item.get("conversationId")
            if not email_id or email_id in seen:
                continue
            sender = item.get("sender") or "unknown"
            contact_threads[sender].append(item)
            seen.add(email_id)
            new_count += 1

        if not contact_threads:
            print(f"📭 No new {source.title()} emails found.")
            return 0

        # Summarize per contact
        for contact_email, messages in contact_threads.items():
            # Summarize each thread safely
            for msg in messages:
                thread_id = msg.get(id_key) or msg.get("threadId") or msg.get("conversationId")
                safe_summarize_thread(source, contact_email, thread_id, thread_obj=[msg])

            # Update contact summary
            result = summarize_contact_logic(
                source,
                contact_email,
                fetch_fn=fetch_fn,
                top=50,
                force_refresh=True  # always refresh when new email arrives
            )

            # Save cache metadata
            summaries[f"{source}:{contact_email}"] = {
                "count": len(messages),
                "last_summary": datetime.now(timezone.utc).isoformat(),
                "contact_summary": result.get("contact_summary", "")
            }

            # Update MCP live cache
            try:
                mcp.cache_contact_summary = getattr(mcp, "cache_contact_summary", {})
                mcp.cache_contact_summary[f"{source}:{contact_email}"] = result.get("contact_summary", "")
            except Exception as e:
                print(f"[MCP ERROR] Failed to update contact summary for {contact_email}: {e}")

        print(f"✅ Done summarizing {new_count} new {source.title()} emails across {len(contact_threads)} contacts.")
        return new_count

    except Exception as e:
        print(f"[ERROR] {source.title()} summarization failed: {e}")
        return 0


# -----------------------------
# Unified loop (Gmail + Outlook)
# -----------------------------
def run_unified_agent():
    gmail_conn = GmailConnector()
    outlook_conn = OutlookConnector()
    cache = load_cache()

    while True:
        print("\n============================")
        print("🤖 Unified Email Summarizer Running")
        print("============================")

        # Auto-clean expired cache before each cycle
        try:
            getattr(mcp, "summarizer", None)._cleanup_expired_cache()
        except Exception:
            pass

        # Gmail
        gmail_new = summarize_platform(
            "gmail",
            gmail_conn,
            cache,
            list_fn=lambda: gmail_conn.list_threads(max_results=20),
            fetch_fn=gmail_conn.fetch_threads_by_id
        )

        # Outlook
        outlook_new = summarize_platform(
            "outlook",
            outlook_conn,
            cache,
            list_fn=lambda: outlook_conn.list_messages(top=20),
            fetch_fn=outlook_conn.get_message
        )

        total_new = gmail_new + outlook_new
        save_cache(cache)

        print("\n📊 Cycle Summary:")
        print(f"  Gmail new: {gmail_new}")
        print(f"  Outlook new: {outlook_new}")
        print(f"  Total new this round: {total_new}")
        print(f"  Last updated: {datetime.now(timezone.utc).isoformat()}")
        print("\n💤 Sleeping for 2 minutes...\n")

        time.sleep(120)  # 2 minutes


if __name__ == "__main__":
    run_unified_agent()
