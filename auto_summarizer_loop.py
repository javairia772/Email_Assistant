# auto_summarizer_loop.py
import os
import time
import json
from datetime import datetime, timezone
from collections import defaultdict, Counter
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic
from server import mcp
from integrations.cache_to_sheets import push_cached_summaries_to_sheets
from classifier.email_classifier import classify_email
from providers.mcp_summaries_provider import McpSummariesProvider

# -----------------------------
# Cache file
# -----------------------------
SUMMARY_CACHE = "Summaries/summaries_cache.json"

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
def load_cache():
    """Load cache safely and ensure 'seen' entries are sets."""
    os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)
    if not os.path.exists(SUMMARY_CACHE):
        print("[WARN] No cache file found; starting fresh.")
        return {"seen": {"gmail": set(), "outlook": set()}, "summaries": {}}

    try:
        with open(SUMMARY_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure 'seen' exists and convert lists to sets
        seen = data.get("seen", {})
        seen_gmail = set(seen.get("gmail", []))
        seen_outlook = set(seen.get("outlook", []))

        # Handle summaries
        summaries = data.get("summaries", {})
        if isinstance(summaries, list):
            new_summaries = {}
            for entry in summaries:
                key = f"{entry.get('source')}:{entry.get('email')}"
                new_summaries[key] = entry
            summaries = new_summaries

        return {
            "seen": {
                "gmail": seen_gmail,
                "outlook": seen_outlook
            },
            "summaries": summaries
        }

    except Exception as e:
        print(f"[ERROR] Could not load cache: {e}")
        os.rename(SUMMARY_CACHE, SUMMARY_CACHE + ".corrupt")
        return {"seen": {"gmail": set(), "outlook": set()}, "summaries": {}}


def save_cache(data):
    """Save summaries and seen sets safely to JSON."""
    os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)

    # Convert sets to lists for JSON serialization
    safe_data = {
        "seen": {
            "gmail": list(data["seen"].get("gmail", [])),
            "outlook": list(data["seen"].get("outlook", []))
        },
        "summaries": data.get("summaries", {}),
        "last_updated": data.get("last_updated")
    }

    with open(SUMMARY_CACHE, "w", encoding="utf-8") as f:
        json.dump(safe_data, f, indent=2, ensure_ascii=False)


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

    # Ensure seen is a set
    if isinstance(cache["seen"].get(source), list):
        cache["seen"][source] = set(cache["seen"][source])
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

            sender = (
                item.get("sender")
                or (item.get("messages", [{}])[0].get("sender") if item.get("messages") else None)
                or "unknown"
            )

            contact_threads[sender].append(item)
            seen.add(email_id)
            new_count += 1

        if not contact_threads:
            print(f"📭 No new {source.title()} emails found.")
            return 0

        # Summarize per contact
        for contact_email, messages in contact_threads.items():
            roles = []
            importances = []
            role_confs = []
            importance_confs = []

            # Track latest date for this contact
            latest_date = None

            for msg in messages:
                thread_id = msg.get(id_key) or msg.get("threadId") or msg.get("conversationId")
                safe_summarize_thread(source, contact_email, thread_id, thread_obj=[msg])

                # Classify role & importance
                sender = msg.get("sender", contact_email)
                subject = msg.get("subject", "")
                body = msg.get("snippet", "") or (msg.get("body", "") if msg.get("body") else "")

                try:
                    classification = classify_email(sender, subject, body)
                except Exception as e:
                    print(f"[Classifier ERROR] Failed to classify email from {sender}: {e}")
                    classification = {"role": "Unknown", "importance": "Unknown", "role_confidence": 0, "importance_confidence": 0}

                msg["role"] = classification["role"]
                msg["importance"] = classification["importance"]
                msg["role_confidence"] = classification.get("role_confidence", 0)
                msg["importance_confidence"] = classification.get("importance_confidence", 0)

                roles.append(msg["role"])
                importances.append(msg["importance"])
                role_confs.append(msg["role_confidence"])
                importance_confs.append(msg["importance_confidence"])

                # Attempt to parse any date-like fields in the message and update latest_date
                for key in ["date", "timestamp", "last_modified", "created_at"]:
                    if key in msg:
                        dt = _parse_date(msg[key])
                        if dt and (latest_date is None or dt > latest_date):
                            latest_date = dt

            # Determine aggregated role & importance for the contact
            contact_role = Counter(roles).most_common(1)[0][0] if roles else "Unknown"
            contact_importance = Counter(importances).most_common(1)[0][0] if importances else "Unknown"
            contact_role_conf = sum(role_confs)/len(role_confs) if role_confs else 0
            contact_importance_conf = sum(importance_confs)/len(importance_confs) if importance_confs else 0

            # Generate contact summary
            result = summarize_contact_logic(
                source,
                contact_email,
                fetch_fn=fetch_fn,
                top=50,
                force_refresh=True
            )

            # Build thread_summaries with correct timestamps (use parsed dates when available)
            thread_summaries = []
            for msg in messages:
                thread_id = msg.get(id_key) or msg.get("threadId") or msg.get("conversationId")

                # Prefer any date-like field from the message
                thread_dt = None
                for key in ["date", "timestamp", "last_modified", "created_at"]:
                    if key in msg:
                        thread_dt = _parse_date(msg[key])
                        if thread_dt:
                            break

                # If not found, try in nested message structure (e.g., msg['messages'][0])
                if thread_dt is None and isinstance(msg.get("messages"), list) and msg["messages"]:
                    nested = msg["messages"][0]
                    for key in ["date", "timestamp", "last_modified", "created_at"]:
                        if key in nested:
                            thread_dt = _parse_date(nested[key])
                            if thread_dt:
                                break

                # Final fallback to current UTC time
                thread_ts_iso = (thread_dt or datetime.now(timezone.utc)).isoformat()

                thread_summaries.append({
                    "thread_id": thread_id,
                    "subject": msg.get("subject", ""),
                    "body": msg.get("snippet", "") or msg.get("body", ""),
                    "summary": msg.get("summary", result.get("contact_summary", "")),
                    "role": msg["role"],
                    "importance": msg["importance"],
                    "role_confidence": msg["role_confidence"],
                    "importance_confidence": msg["importance_confidence"],
                    "timestamp": thread_ts_iso
                })

            # If we didn't find a latest_date from per-message parsing, check result or entry-level fields:
            if latest_date is None:
                # try to see if contact-level result contains a date field (rare)
                for key in ["last_summary", "timestamp", "date"]:
                    val = result.get(key)
                    if val:
                        dt = _parse_date(val)
                        if dt and (latest_date is None or dt > latest_date):
                            latest_date = dt

            # Final fallback to now if no date info available
            final_last_summary_iso = (latest_date.isoformat() if latest_date else datetime.now(timezone.utc).isoformat())

            # Update summaries cache for this contact
            summaries[f"{source}:{contact_email}"] = {
                "count": len(messages),
                "threads": thread_summaries,
                "contact_summary": result.get("contact_summary", ""),
                "role": contact_role,
                "importance": contact_importance,
                "role_confidence": round(contact_role_conf, 3),
                "importance_confidence": round(contact_importance_conf, 3),
                "last_summary": final_last_summary_iso,
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
    provider = McpSummariesProvider()
    cache = load_cache()  # load existing cache first

    while True:
        print("\n============================")
        print("🤖 Unified Email Summarizer Running")
        print("============================")

        # ✅ Check which emails are already cached to avoid re-summarizing
        try:
            # Pass existing cache to provider so it can skip already-summarized emails
            new_summaries = provider.get_summaries(limit=20, existing_cache=cache)
        except Exception as e:
            print(f"[ERROR] Failed to fetch summaries: {e}")
            time.sleep(10)
            continue

        # Merge into existing cache
        for s in new_summaries:
            source = s.get("source", "unknown")
            email = s.get("email", "unknown")
            key = f"{source}:{email}"

            cache["summaries"][key] = s
            thread_id = s.get("id")
            if thread_id:
                cache["seen"].setdefault(source, set()).add(thread_id)

        cache["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Save local cache
        save_cache(cache)

        # Push to Google Sheets
        try:
            print("⬆️  Syncing cached summaries to Google Sheets...")
            push_cached_summaries_to_sheets(cache["summaries"])  # accept dict format
            print("✅ Google Sheets updated successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to sync to Google Sheets: {e}")

        print(f"📊 Cycle Summary: {len(new_summaries)} contacts processed")
        print(f"Last updated: {datetime.now(timezone.utc).isoformat()}")
        print("\n💤 Sleeping for 10 seconds...\n")
        time.sleep(10)

if __name__ == "__main__":
    run_unified_agent()
