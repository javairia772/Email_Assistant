# auto_summarizer_loop.py
import os
import time
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Summarizer.groq_summarizer import GroqSummarizer
from server import mcp  # MCP instance
from integrations.cache_to_sheets import push_cached_summaries_to_sheets


summarizer = GroqSummarizer()
mcp.summarizer = summarizer

# -----------------------------
# Cache helpers
# -----------------------------
def load_cache():
    # Load thread/contact cache
    if os.path.exists("Summaries/summaries_cache.json"):
        with open("Summaries/summaries_cache.json", "r", encoding="utf-8") as f:
            summaries_cache = json.load(f)
    else:
        summaries_cache = {}

    # Load seen threads
    if os.path.exists("Summaries/seen_threads.json"):
        with open("Summaries/seen_threads.json", "r", encoding="utf-8") as f:
            seen_threads = json.load(f)
            seen_threads["gmail"] = set(seen_threads.get("gmail", []))
            seen_threads["outlook"] = set(seen_threads.get("outlook", []))
    else:
        seen_threads = {"gmail": set(), "outlook": set()}

    return summaries_cache, seen_threads


def save_cache(summaries_cache, seen_threads, summaries_data=None):
    """
    Save all cache files safely, with backup (max 2 backups per file).
    """
    # Save summaries_cache.json
    safe_save_json("Summaries/summaries_cache.json", summaries_cache)

    # Save seen_threads.json (convert sets back to lists)
    safe_save_json("Summaries/seen_threads.json", {k: list(v) for k, v in seen_threads.items()})

    # Save summaries_ID.json if provided
    if summaries_data:
        safe_save_json("Summaries/summaries_ID.json", summaries_data)


def safe_save_json(file_path, data, backup_folder="Backup", max_backups=2):
    """
    Safely save JSON data with backup only if content has changed.
    Keeps only the latest `max_backups` backup files.
    """
    import glob

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    os.makedirs(backup_folder, exist_ok=True)

    # Check if file exists and content is the same
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            if existing_data == data:
                # No change, skip saving
                return
        except Exception:
            # If file is corrupt, continue to overwrite
            pass

        # Backup old file
        backup_file = os.path.join(
            backup_folder,
            f"{Path(file_path).name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
        )
        shutil.copy(file_path, backup_file)

        # Clean up old backups, keep only `max_backups`
        backups = sorted(
            glob.glob(os.path.join(backup_folder, f"{Path(file_path).name}_*.bak")),
            reverse=True
        )
        for old_backup in backups[max_backups:]:
            os.remove(old_backup)

    # Save new file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -----------------------------
# Helper: exponential backoff for rate-limited Groq calls
# -----------------------------
def safe_summarize_thread(source, contact_email, thread_id, thread_obj=None, max_retries=5):
    delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            return summarizer.summarize_thread(
                thread_emails=thread_obj or [],
                source=source,
                contact_email=contact_email,
                thread_id=thread_id
            )
        except Exception as e:
            msg = str(e)
            if "rate_limit" in msg.lower() or "429" in msg:
                print(f"⚠️ Groq rate limit hit for {thread_id}, retrying in {delay}s (attempt {attempt})")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[ERROR] Failed summarizing thread {thread_id}: {msg}")
                return {"error": msg}
    return {"error": f"Max retries exceeded for {thread_id}"}



# -----------------------------
# Summarize a batch of threads/emails (refactored)
# -----------------------------
def summarize_platform(source, connector, summaries_cache, seen_threads, list_fn, fetch_fn, id_key="id"):
    """
    Summarize a batch of threads/emails for a platform (Gmail/Outlook),
    preserving previous threads and adding message snippets.
    """
    print(f"\n🔍 Checking {source.title()} for new emails...")

    seen = seen_threads[source]
    summaries = summaries_cache
    new_count = 0
    summaries_ID_list = []

    try:
        # 1️⃣ List recent threads/messages
        threads = list_fn()
        if not threads:
            print(f"📭 No new {source.title()} emails found.")
            return 0, []

        # 2️⃣ Group messages by sender/contact
        contact_threads = defaultdict(list)
        for item in threads:
            email_id = item.get(id_key) or item.get("threadId") or item.get("conversationId")
            if not email_id or email_id in seen:
                continue

            sender = item.get("sender") or (item.get("messages", [{}])[0].get("sender") if item.get("messages") else "unknown")
            contact_threads[sender].append(item)
            seen.add(email_id)
            new_count += 1

        if not contact_threads:
            print(f"📭 No new {source.title()} emails found.")
            return 0, []

        # 3️⃣ Process each contact
        for contact_email, messages in contact_threads.items():
            print(f"📬 Summarizing contact: {contact_email} ({len(messages)} threads)")

            contact_id = f"{source}:{contact_email}"

            # Load previous threads to preserve history
            previous_threads = summaries.get(contact_id, {}).get("threads", [])
            all_threads = previous_threads.copy()

            for msg in messages:
                thread_id = msg.get(id_key) or msg.get("threadId") or msg.get("conversationId")

                # Fetch full parsed messages with body
                if source == "gmail":
                    thread_emails = connector.fetch_threads_by_id(thread_id)
                else:
                    thread_emails = msg.get("messages", [msg])

                # Add snippet to each message
                for m in thread_emails:
                    m["snippet"] = m.get("body", "")[:300]

                # Summarize the thread
                thread_summary = safe_summarize_thread(source, contact_email, thread_id, thread_obj=thread_emails)

                # Append to all_threads
                all_threads.append({
                    "id": thread_id,
                    "messages": thread_emails,
                    "summary": thread_summary
                })

            # Build contact object
            contact_obj = {"email": contact_email, "threads": all_threads}

            # Generate contact-level summary
            contact_summary = connector.summarizer.summarize_contact(contact_obj, source=source, force=True)

            # Update cache
            summaries[contact_id] = {
                "count": len(all_threads),
                "last_summary": datetime.now(timezone.utc).isoformat(),
                "contact_summary": contact_summary,
                # "threads": all_threads
            }

            # Update MCP memory
            mcp.cache_contact_summary = getattr(mcp, "cache_contact_summary", {})
            mcp.cache_contact_summary[contact_id] = contact_summary

            # Append for summaries_ID.json
            summaries_ID_list.append({
                **contact_obj,
                "contact summary": contact_summary,
                "source": source,
                "id": contact_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

        print(f"✅ Done summarizing {new_count} new {source.title()} emails across {len(contact_threads)} contacts.")
        return new_count, summaries_ID_list

    except Exception as e:
        print(f"[ERROR] {source.title()} summarization failed: {e}")
        return 0, []



# -----------------------------
# Unified loop (Gmail + Outlook)
# -----------------------------
def run_unified_agent():
    gmail_conn = GmailConnector()
    outlook_conn = OutlookConnector()

    gmail_conn.summarizer = summarizer
    outlook_conn.summarizer = summarizer
    summaries_cache, seen_threads = load_cache()

    # Load existing summaries_ID.json to accumulate all threads
    summaries_ID_file = "Summaries/summaries_ID.json"
    if os.path.exists(summaries_ID_file):
        try:
            with open(summaries_ID_file, "r", encoding="utf-8") as f:
                summaries_ID_list = json.load(f)
        except Exception:
            summaries_ID_list = []
    else:
        summaries_ID_list = []

    while True:
        print("\n============================")
        print("🤖 Unified Email Summarizer Running")
        print("============================")

        # Auto-clean expired cache before each cycle
        try:
            getattr(mcp, "summarizer", None)._cleanup_expired_cache()
        except Exception:
            pass

        # Summarize Gmail
        gmail_new, gmail_summaries = summarize_platform(
            "gmail",
            gmail_conn,
            summaries_cache,
            seen_threads,
            list_fn=lambda: gmail_conn.list_threads(max_results=50),
            fetch_fn=gmail_conn.fetch_threads_by_id
        )

        # Summarize Outlook
        outlook_new, outlook_summaries = summarize_platform(
            "outlook",
            outlook_conn,
            summaries_cache,
            seen_threads,
            list_fn=lambda: outlook_conn.list_messages(top=10),
            fetch_fn=outlook_conn.get_message
        )

        # Combine new summaries for this cycle
        new_summaries = gmail_summaries + outlook_summaries
        if new_summaries:
            summaries_ID_list.extend(new_summaries)  # Keep historical threads

        total_new = gmail_new + outlook_new

        # Save caches and accumulated summaries safely
        save_cache(summaries_cache, seen_threads, summaries_data=summaries_ID_list)

        # Push updated summaries to Google Sheets
        try:
            print("⬆️  Syncing cached summaries to Google Sheets...")
            push_cached_summaries_to_sheets()
            print("✅ Google Sheets updated successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to sync to Google Sheets: {e}")

        # Cycle summary
        print("\n📊 Cycle Summary:")
        print(f"  Gmail new: {gmail_new}")
        print(f"  Outlook new: {outlook_new}")
        print(f"  Total new this round: {total_new}")
        print(f"  Last updated: {datetime.now(timezone.utc).isoformat()}")
        print("\n💤 Sleeping for 2 minutes...\n")

        time.sleep(20)  # 20 seconds


if __name__ == "__main__":
    run_unified_agent()
