import json
import os
from integrations.google_sheets import upsert_summaries
from datetime import datetime


CACHE_PATH = "Summaries/summaries_cache.json"

def push_cached_summaries_to_sheets(sheet_name="EmailAssistantSummaries"):
    """Read local summary_cache.json (list-based) and upsert summaries into Google Sheets."""
    if not os.path.exists(CACHE_PATH):
        print("[WARN] No summaries_cache.json found.")
        return

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        try:
            cache_data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Could not parse cache JSON: {e}")
            return

    if not isinstance(cache_data, list):
        print("[ERROR] Cache file format invalid: expected a list.")
        return

    rows = []
    for entry in cache_data:
        if not isinstance(entry, dict):
            continue

        # Case 1: Simple summary object
        if "email" not in entry and "summary" in entry:
            rows.append({
                "id": f"cache:{entry.get('timestamp', datetime.utcnow().timestamp())}",
                "email": "unknown",
                "role": "Student",
                "summary": entry.get("summary", ""),
                "date": datetime.utcfromtimestamp(
                    entry.get("timestamp", datetime.utcnow().timestamp())
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "source": "gmail",
            })
            continue

        # Case 2: Structured contact summary
        email = entry.get("email", "unknown")
        threads = entry.get("threads", [])
        last_date = None
        all_bodies = []

        # Extract last message date & content summary
        for thread in threads:
            messages = thread.get("messages", [])
            for msg in messages:
                body = msg.get("body")
                if body:
                    all_bodies.append(body[:300])  # only keep short snippet
                msg_date = msg.get("date")
                try:
                    last_date = msg_date or last_date
                except Exception:
                    pass

        rows.append({
            "id": threads[0]["id"] if threads else f"gmail:{email}",
            "email": email,
            "role": "Student",
            "summary": entry.get("summary", " ".join(all_bodies)[:2000] or "No summary."),
            "date": last_date or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "gmail",
        })

    if not rows:
        print("[INFO] No valid cached summaries to push.")
        return

    print(f"[INFO] Uploading {len(rows)} summaries to Google Sheets...")
    try:
        upsert_summaries(rows)
        print("[Sheets] ✅ Successfully pushed cache to Google Sheets.")
    except Exception as e:
        print(f"[Sheets] ❌ Error upserting summaries: {e}")


if __name__ == "__main__":
    push_cached_summaries_to_sheets("EmailAssistantSummaries")


