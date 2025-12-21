# auto_summarizer_loop.py
import json
import os
import time
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic
from server import mcp
from integrations.cache_to_sheets import push_cached_summaries_to_sheets
from classifier.email_classifier import classify_email
from providers.mcp_summaries_provider import McpSummariesProvider
from integrations.google_calendar import GoogleCalendar
from dateutil import parser
from typing import Optional, Dict, Any

# -----------------------------
# Cache file
# -----------------------------
SUMMARY_CACHE = "Summaries/summaries_cache.json"

def load_cache():
    os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)

    if not os.path.exists(SUMMARY_CACHE):
        return {
            "summaries": {},
            "seen": {"gmail": set(), "outlook": set()},
            "processed_emails": set(),
            "calendar_events": {},
            "last_updated": None
        }

    try:
        with open(SUMMARY_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "summaries": data.get("summaries", {}),
            "seen": {
                "gmail": set(data.get("seen", {}).get("gmail", [])),
                "outlook": set(data.get("seen", {}).get("outlook", []))
            },
            "processed_emails": set(data.get("processed_emails", [])),
            "calendar_events": data.get("calendar_events", {}),
            "last_updated": data.get("last_updated")
        }

    except Exception as e:
        print(f"[ERROR] Cache corrupted: {e}")
        return {
            "summaries": {},
            "seen": {"gmail": set(), "outlook": set()},
            "processed_emails": set(),
            "calendar_events": {},
            "last_updated": None
        }

def save_cache(cache):
    os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)

    safe_cache = {
        "summaries": cache.get("summaries", {}),
        "seen": {
            "gmail": list(cache.get("seen", {}).get("gmail", [])),
            "outlook": list(cache.get("seen", {}).get("outlook", []))
        },
        "processed_emails": list(cache.get("processed_emails", [])),
        "calendar_events": cache.get("calendar_events", {}),
        "last_updated": cache.get("last_updated")
    }

    with open(SUMMARY_CACHE, "w", encoding="utf-8") as f:
        json.dump(safe_cache, f, indent=2, ensure_ascii=False)

# -----------------------------
# Date parsing helper
# -----------------------------
def _parse_date(date_str):
    """Parse date string to datetime object (UTC) handling multiple formats."""
    if not date_str:
        return None

    if isinstance(date_str, datetime):
        return date_str.astimezone(timezone.utc) if date_str.tzinfo else date_str.replace(tzinfo=timezone.utc)

    date_formats = [
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%d %H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%d-%m-%Y %H:%M',
        '%m/%d/%Y %I:%M %p',
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue

    # Last attempt: if it's numeric timestamp (seconds or milliseconds)
    try:
        # Accept ints/floats as seconds since epoch or ms as >1e12
        ts = float(date_str)
        if ts > 1e12:  # milliseconds
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        pass

    # Couldn't parse
    return None

# -----------------------------
# Cache helpers
# -----------------------------
# def load_cache():
#     """Load cache safely and ensure 'seen' entries are sets."""
#     os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)
#     if not os.path.exists(SUMMARY_CACHE):
#         print("[WARN] No cache file found; starting fresh.")
#         return {"seen": {"gmail": set(), "outlook": set()}, "summaries": {}}

#     try:
#         with open(SUMMARY_CACHE, "r", encoding="utf-8") as f:
#             data = json.load(f)

#         # Ensure 'seen' exists and convert lists to sets
#         seen = data.get("seen", {})
#         seen_gmail = set(seen.get("gmail", []))
#         seen_outlook = set(seen.get("outlook", []))

#         # Handle summaries
#         summaries = data.get("summaries", {})
#         if isinstance(summaries, list):
#             new_summaries = {}
#             for entry in summaries:
#                 key = f"{entry.get('source')}:{entry.get('email')}"
#                 new_summaries[key] = entry
#             summaries = new_summaries

#         return {
#             "seen": {
#                 "gmail": seen_gmail,
#                 "outlook": seen_outlook
#             },
#             "summaries": summaries
#         }

#     except Exception as e:
#         print(f"[ERROR] Could not load cache: {e}")
#         os.rename(SUMMARY_CACHE, SUMMARY_CACHE + ".corrupt")
#         return {"seen": {"gmail": set(), "outlook": set()}, "summaries": {}}




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



def process_calendar_events(summary: dict, cache: dict) -> None:
    """Process calendar events from email summary."""
    try:
        print("\n🔍 Processing email for calendar events...")

        # Initialize calendar client
        calendar = GoogleCalendar()

        # Get the most recent message in the thread
        threads = summary.get('threads', [])
        if not threads:
            print("  ℹ️ No threads found in summary")
            return

        latest_message = threads[0]
        subject = latest_message.get('subject', '') or latest_message.get('last_subject', '')

        body = (
            latest_message.get('body')
            or latest_message.get('last_body')
            or latest_message.get('snippet')
            or latest_message.get('preview', '')
        )

        if not body:
            print("  ⚠️ No message body found in email")
            return

        print(f"  📧 Processing email with subject: {subject[:50]}...")
        print(f"  📝 Body preview: {body[:100]}...")

        # Extract meeting info from email body
        meeting_info = calendar.extract_meeting_info(body)
        if not meeting_info:
            print("  ℹ️ No meeting information found in email")
            return

        print(f"  ✅ Found meeting info: {meeting_info}")

        # Deduplication key
        source = summary.get('source', 'unknown')
        thread_id = summary.get('id')
        start_time = meeting_info.get('start_time')

        if not all([source, thread_id, start_time]):
            missing = [f for f, v in zip(['source','thread_id','start_time'], [source,thread_id,start_time]) if not v]
            print(f"  ⚠️ Missing required fields: {', '.join(missing)}")
            return

        event_key = f"{source}:{thread_id}:{start_time}"

        # Ensure cache structures exist
        cache.setdefault('calendar_events', {})
        cache.setdefault('processed_emails', set())

        # Skip if event already exists
        if event_key in cache['calendar_events']:
            print(f"  ℹ️ Calendar event already exists in cache for: {subject}")
            return

        # Create event
        event_data = {
            'summary': meeting_info.get('summary', subject[:100]),
            'description': f"Event created from email:\n\n{subject}\n\n{body}",
            'start_time': start_time,
            'end_time': meeting_info.get('end_time', (datetime.fromisoformat(start_time) + timedelta(hours=1)).isoformat())
        }

        result = calendar.create_event(event_data)

        if result.get('success'):
            print(f"\n✅ Successfully created calendar event: {subject}")
            if 'html_link' in result:
                print(f"   🔗 {result['html_link']}")

            # Add to cache immediately
            cache['calendar_events'][event_key] = {
                'created_at': datetime.now(timezone.utc).isoformat(),
                'subject': subject,
                'start_time': start_time,
                'email_thread_id': thread_id,
                'email_subject': subject,
                'processed_at': datetime.now(timezone.utc).isoformat()
            }

            # Save immediately after adding
            save_cache(cache)
            print(f"  💾 Saved event to cache with key: {event_key}")

        else:
            print(f"\n❌ Failed to create calendar event. Error: {result.get('error', 'Unknown error')}")
            if 'details' in result:
                print(f"  Details: {result['details']}")

    except Exception as e:
        print(f"⚠️ Error processing calendar event: {e}")
        import traceback
        traceback.print_exc()



# -----------------------------
# Unified loop (Gmail + Outlook)
# -----------------------------

def run_unified_agent():
    provider = McpSummariesProvider()
    cache = load_cache()  # load existing cache first

    # Ensure cache structures exist
    cache.setdefault('calendar_events', {})
    cache.setdefault('processed_emails', set())
    cache.setdefault('seen', {'gmail': set(), 'outlook': set()})

    # Ensure processed_emails is a set
    if isinstance(cache['processed_emails'], list):
        cache['processed_emails'] = set(cache['processed_emails'])
    elif not isinstance(cache['processed_emails'], set):
        cache['processed_emails'] = set()

    print(f"ℹ️ Loaded {len(cache['processed_emails'])} processed emails from cache")
    print(f"ℹ️ Loaded {len(cache.get('calendar_events', {}))} calendar events from cache")

    while True:
        print("\n============================")
        print("🤖 Unified Email Summarizer Running")
        print("============================")

        try:
            new_summaries = provider.get_summaries(limit=20, existing_cache=cache)

            if not new_summaries:
                print("ℹ️ No new emails to process")
                time.sleep(10)
                continue

            print(f"\n📨 Found {len(new_summaries)} new email(s) to process")

            for summary in new_summaries:
                thread_id = summary.get('id')
                if not thread_id:
                    print("⚠️ Skipping email with no thread ID")
                    continue

                if thread_id in cache.get('processed_emails', set()):
                    print(f"ℹ️ Skipping already processed email (Thread ID: {thread_id})")
                    continue

                subject = summary.get('subject', 'No subject')
                print(f"\n📧 Processing new email: {subject}")

                try:
                    process_calendar_events(summary, cache)

                    # Mark as processed and save immediately
                    cache['processed_emails'].add(thread_id)
                    save_cache(cache)
                    print(f"✅ Marked email as processed (Thread ID: {thread_id})")

                except Exception as e:
                    print(f"⚠️ Error processing calendar events for email: {e}")
                    import traceback
                    traceback.print_exc()
                    print(f"⚠️ Email will be retried in the next cycle (Thread ID: {thread_id})")

        except Exception as e:
            print(f"[ERROR] Failed to fetch summaries: {e}")
            time.sleep(10)
            continue

        # Merge new summaries into cache
        for s in new_summaries:
            source = s.get("source", "unknown")
            email = s.get("email", "unknown")
            key = f"{source}:{email}"

            cache["summaries"][key] = s
            thread_id = s.get("id")
            if thread_id:
                cache['seen'].setdefault(source, set())
                cache['seen'][source].add(thread_id)

        cache["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Save cache after merging summaries
        save_cache(cache)

        # Push to Google Sheets
        try:
            print("⬆️  Syncing cached summaries to Google Sheets...")
            push_cached_summaries_to_sheets(cache["summaries"])
            print("✅ Google Sheets updated successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to sync to Google Sheets: {e}")

        print(f"📊 Cycle Summary: {len(new_summaries)} contacts processed")
        print(f"Last updated: {datetime.now(timezone.utc).isoformat()}")
        print("\n💤 Sleeping for 10 seconds...\n")
        time.sleep(10)


if __name__ == "__main__":
    run_unified_agent()
