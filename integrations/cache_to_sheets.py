import json
import os
from integrations.google_sheets import upsert_summaries
from datetime import datetime

# Path to summaries_ID.json
CACHE_FILE = "Summaries/summaries_ID.json"


def push_cached_summaries_to_sheets(sheet_name="EmailAssistantSummaries"):
    """Read summaries_ID.json and upsert contact summaries to Google Sheets."""
    
    if not os.path.exists(CACHE_FILE):
        print(f"[WARN] {CACHE_FILE} not found.")
        return

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Could not parse JSON: {e}")
            return

    if not isinstance(data, list):
        print("[ERROR] JSON format invalid: expected a list of contact summaries.")
        return

    rows = []

    for contact in data:
        email = contact.get("email", "unknown")
        role = "Student"  # or derive dynamically if needed
        contact_summary = contact.get("contact summary") or "No summary available."
        threads = contact.get("threads", [])
        
        # Get latest date from all threads/messages
        last_date = None
        for thread in threads:
            for msg in thread.get("messages", []):
                msg_date = msg.get("date")
                if msg_date:
                    last_date = msg_date  # just take last seen

        # Use first thread id as unique id
        contact_id = threads[0]["id"] if threads else f"gmail:{email}"

        rows.append({
            "Id": contact_id,
            "Email": email,
            "Role": role,
            "Summary": contact_summary,
            "Date": last_date or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            # "source": contact.get("source", "gmail"),
        })

    if not rows:
        print("[INFO] No contact summaries to push.")
        return

    print(f"[INFO] Uploading {len(rows)} contact summaries to Google Sheets...")
    try:
        upsert_summaries(rows)
        print("[Sheets] ✅ Successfully pushed contact summaries.")
    except Exception as e:
        print(f"[Sheets] ❌ Error upserting summaries: {e}")


if __name__ == "__main__":
    push_cached_summaries_to_sheets()
