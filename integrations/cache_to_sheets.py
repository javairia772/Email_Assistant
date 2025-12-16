import json
import os
from datetime import datetime, timezone
from integrations.google_sheets import upsert_summaries


CACHE_PATH = "Summaries/summaries_cache.json"


def _parse_date(date_str):
    """Parse date string to datetime object, handling multiple formats."""
    if not date_str:
        return None

    if isinstance(date_str, datetime):
        return date_str.astimezone(timezone.utc) if date_str.tzinfo else date_str.replace(tzinfo=timezone.utc)

    date_formats = [
        '%Y-%m-%dT%H:%M:%S%z',      # 2023-11-06T13:18:25+05:00
        '%Y-%m-%d %H:%M:%S%z',      # 2023-11-06 13:18:25+05:00
        '%Y-%m-%dT%H:%M:%S.%fZ',    # 2023-11-06T08:18:25.123456Z
        '%Y-%m-%dT%H:%M:%SZ',       # 2023-11-06T08:18:25Z
        '%Y-%m-%d %H:%M:%S',        # 2023-11-06 13:18:25
        '%Y-%m-%d',                 # 2023-11-06
        '%d-%m-%Y %H:%M',           # 06-11-2023 13:18
        '%m/%d/%Y %I:%M %p',        # 11/06/2023 01:18 PM
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue

    print(f"[WARN] Could not parse date: {date_str}")
    return None


def push_cached_summaries_to_sheets(summaries_dict=None):
    """Push summaries cache to Google Sheets with correct last thread date."""

    # Load cache if not provided
    if summaries_dict is None:
        if not os.path.exists(CACHE_PATH):
            print("[WARN] No summaries_cache.json found.")
            return

        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            try:
                cache_data = json.load(f)
            except Exception as e:
                print(f"[ERROR] Could not parse cache JSON: {e}")
                return

        summaries_dict = cache_data.get("summaries", cache_data)

    # Convert dict to list if needed
    summaries_list = list(summaries_dict.values()) if isinstance(summaries_dict, dict) else summaries_dict

    if not isinstance(summaries_list, list):
        print("[ERROR] Cache file format invalid: expected a list or dict of summaries.")
        return

    rows = []

    for entry in summaries_list:
        if not isinstance(entry, dict):
            continue

        email = entry.get("email", "unknown")
        source = entry.get("source", "unknown")
        threads = entry.get("threads", [])

        # Find the most recent thread date
        latest_date = None
        for thread in threads:
            for field in ['date', 'timestamp', 'last_modified', 'created_at']:
                if field in thread:
                    dt = _parse_date(thread[field])
                    if dt and (latest_date is None or dt > latest_date):
                        latest_date = dt

        # If no thread dates, fallback to entry date or now
        if latest_date is None:
            for field in ['date', 'timestamp', 'last_modified', 'created_at']:
                if field in entry:
                    dt = _parse_date(entry[field])
                    if dt:
                        latest_date = dt
                        break

        # Format the final date
        last_updated = (
            latest_date.isoformat()
            if latest_date
            else datetime.now(timezone.utc).isoformat()
        )

        row = {
            "id": entry.get("id", f"{source}:{email}"),
            "email": email,
            "source": source,
            "role": entry.get("role", "Unknown"),
            "role_confidence": entry.get("role_confidence", 0),
            "contact_summary": entry.get("summary", "") or entry.get("contact_summary", ""),
            "threads": threads,
            "last_summary": last_updated,  # ✅ Actual last thread date
        }
        rows.append(row)

    if not rows:
        print("[INFO] No valid cached summaries to push.")
        return

    print(f"[INFO] Uploading {len(rows)} summaries to Google Sheets...")
    try:
        upsert_summaries(rows)
        print("[Sheets] ✅ Successfully pushed cache to Google Sheets.")
    except Exception as e:
        print(f"[Sheets] ❌ Error upserting summaries: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    push_cached_summaries_to_sheets()
