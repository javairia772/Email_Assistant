from typing import List, Dict, Optional
import os
from pathlib import Path
import gspread
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from datetime import datetime, timezone
import json

# ---------------------- CONFIG ----------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_NAME = "EmailAssistantSummaries"
WORKSHEET_NAME = "Summaries"

HEADER = [
    "id", 
    "email", 
    "source",
    "role", 
    "role_confidence",
    "contact_summary", 
    "threads",
    "last_summary"
]

OUT_KEYS = HEADER.copy()
FALLBACK_CACHE_PATH = Path(os.getenv("SUMMARY_CACHE_PATH", "Summaries/summaries_cache.json"))


# ---------------------- AUTH ----------------------
def _get_client():
    creds = None
    token_file = os.getenv("GOOGLE_SHEETS_TOKEN", "token_gmail_sheets.pkl")

    print(f"[Sheets] Using environment variables for authentication")
    print(f"[Sheets] Using spreadsheet: {SPREADSHEET_NAME}")
    print(f"[Sheets] Using worksheet: {WORKSHEET_NAME}")

    # Create client config from environment variables (same as Gmail)
    client_config = {
        "installed": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": ["http://localhost:8081/"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Create a temporary credentials file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_creds:
                json.dump(client_config, temp_creds)
                temp_creds_path = temp_creds.name
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(temp_creds_path, SCOPES)
                creds = flow.run_local_server(port=8081)
                with open(token_file, "wb") as token:
                    pickle.dump(creds, token)
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(temp_creds_path)
                except:
                    pass

    return gspread.authorize(creds)


# ---------------------- SPREADSHEET HELPERS ----------------------
def _get_or_create_spreadsheet(gc, spreadsheet_name: Optional[str] = None):
    """Get or create spreadsheet without enumerating the entire drive."""
    target_name = spreadsheet_name or SPREADSHEET_NAME
    try:
        return gc.open(target_name)
    except gspread.SpreadsheetNotFound:
        print(f"[Sheets] Creating new spreadsheet: {target_name}")
        return gc.create(target_name)


def _get_or_create_worksheet(spreadsheet_name: Optional[str] = None, worksheet_name: Optional[str] = None):
    """Safely get worksheet — never resets data."""
    target_spreadsheet = spreadsheet_name or SPREADSHEET_NAME
    target_worksheet = worksheet_name or WORKSHEET_NAME
    try:
        gc = _get_client()
        sh = _get_or_create_spreadsheet(gc, target_spreadsheet)
        try:
            ws = sh.worksheet(target_worksheet)
            print(f"[Sheets] Found worksheet: {target_worksheet}")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=target_worksheet, rows=100, cols=len(HEADER))
            ws.append_row(HEADER)
            print(f"[Sheets] Created new worksheet: {target_worksheet}")
            return ws

        # Header check (non-destructive)
        current_header = [h.strip().lower() for h in ws.row_values(1)]
        expected_header = [h.lower() for h in HEADER]
        if current_header != expected_header:
            print("[Sheets] ⚠ Header mismatch — skipping overwrite to protect data.")
            print(f"Current header: {current_header}")
            print(f"Expected header: {expected_header}")

        return ws

    except Exception as e:
        print(f"[Sheets] ❌ Error initializing worksheet: {e}")
        raise


# ---------------------- DATE HANDLING ----------------------
def _parse_date(date_str):
    """Parse date string to datetime object, handling multiple formats."""
    if not date_str:
        return None

    if isinstance(date_str, datetime):
        return date_str.astimezone(timezone.utc) if date_str.tzinfo else date_str.replace(tzinfo=timezone.utc)

    # Handle the case where the date string is already in ISO 8601 format with timezone
    if isinstance(date_str, str) and '+' in date_str and ':' == date_str[-3:-2]:
        # Remove the colon from the timezone offset (e.g., +00:00 -> +0000)
        date_str = date_str[:-3] + date_str[-2:]
    
    date_formats = [
        '%Y-%m-%dT%H:%M:%S.%f%z',  # With microseconds and timezone
        '%Y-%m-%dT%H:%M:%S%z',     # Without microseconds, with timezone
        '%Y-%m-%d %H:%M:%S%z',     # Space separator, with timezone
        '%Y-%m-%dT%H:%M:%S.%fZ',   # With microseconds, UTC
        '%Y-%m-%dT%H:%M:%SZ',      # Without microseconds, UTC
        '%Y-%m-%d %H:%M:%S',       # Local time without timezone
        '%Y-%m-%d',                # Date only
        '%d-%m-%Y %H:%M',          # European date format
        '%m/%d/%Y %I:%M %p',       # US date format with AM/PM
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


# ---------------------- READ SHEET ----------------------
def read_all_summaries(spreadsheet_name: Optional[str] = None, worksheet_name: Optional[str] = None) -> list[dict]:
    """Read all rows safely from Google Sheets."""
    try:
        ws = _get_or_create_worksheet(spreadsheet_name, worksheet_name)

        # First, get all values to inspect the headers
        all_values = ws.get_all_values()
        if not all_values:
            return _fallback_rows_from_cache()

        # Get the first row as headers and clean them up
        headers = [h.strip() for h in all_values[0]]

        # Handle empty or duplicate headers
        seen = set()
        clean_headers = []
        for i, h in enumerate(headers):
            if not h:  # If header is empty
                clean_headers.append(f"column_{i}")
            elif h in seen:  # If header is duplicate
                clean_headers.append(f"{h}_{i}")
            else:
                clean_headers.append(h)
                seen.add(h)

        # Convert rows to dictionaries with clean headers
        rows = []
        for row in all_values[1:]:  # Skip header row
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(clean_headers):
                    row_dict[clean_headers[i]] = value
                else:
                    row_dict[f"column_{i}"] = value
            rows.append(row_dict)

        if not rows:
            return _fallback_rows_from_cache()

        print(f"[Sheets] ✅ Read {len(rows)} rows (showing up to 5):")
        import pprint; pprint.pprint(rows[:5])
        return rows

    except Exception as e:
        print(f"[Sheets] ❌ Error reading sheet: {str(e)}")
        return _fallback_rows_from_cache()


def _fallback_rows_from_cache() -> List[Dict]:
    if not FALLBACK_CACHE_PATH.exists():
        return []
    try:
        with FALLBACK_CACHE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"[Sheets] ⚠ Fallback cache read failed: {exc}")
        return []

    entries = data.get("summaries", data)
    if isinstance(entries, dict):
        records = list(entries.values())
    elif isinstance(entries, list):
        records = entries
    else:
        return []

    fallback_rows = []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        email = entry.get("email", "")
        if not email:
            continue
        fallback_rows.append({
            "id": entry.get("id") or f"{entry.get('source','unknown')}:{email}",
            "email": email,
            "source": entry.get("source", ""),
            "role": entry.get("role", "Unknown"),
            "role_confidence": entry.get("role_confidence", ""),
            "contact_summary": entry.get("contact_summary") or entry.get("summary") or "",
            "threads": entry.get("threads", []),
            "last_summary": entry.get("last_summary") or entry.get("timestamp") or entry.get("date") or "",
        })
    if fallback_rows:
        print(f"[Sheets] ⚠ Using fallback cache rows ({len(fallback_rows)})")
    return fallback_rows


# ---------------------- UPSERT (ADD/UPDATE) ----------------------
def _merge_summary(old_text: str, new_text: str) -> str:
    """Prefer meaningful summaries over placeholders."""
    placeholder_phrases = ["Summary of", "not available yet"]
    if new_text and not any(p in new_text for p in placeholder_phrases):
        return new_text.strip()
    if old_text and not any(p in old_text for p in placeholder_phrases):
        return old_text.strip()
    return new_text.strip() or old_text.strip()


def _normalize_row_payload(row: Dict) -> Dict:
    """Normalize inbound rows so columns are always present."""
    if not isinstance(row, dict):
        return {}

    def _pick(*keys, default=""):
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return default

    email = str(_pick("email", "Email")).strip()
    source = str(_pick("source", "Source", default="unknown")).strip() or "unknown"
    row_id = str(_pick("id", "Id")).strip()
    if not row_id and email:
        row_id = f"{source}:{email}" if source else email

    contact_summary = _pick("contact_summary", "summary", "contactSummary", default="")
    last_summary = _pick("last_summary", "lastSummary", "timestamp", "date", default="")
    if not last_summary:
        last_summary = datetime.now(timezone.utc).isoformat()

    normalized = {
        "id": row_id,
        "email": email,
        "source": source,
        "role": _pick("role", "Role", default="Unknown"),
        "role_confidence": _pick("role_confidence", "Role_confidence", "roleConfidence", default=0),
        "contact_summary": contact_summary,
        "threads": row.get("threads", []),
        "last_summary": last_summary,
    }
    return normalized


def _serialize_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def _coerce_args(*args, **kwargs):
    """Backwards compatible arg parser for upsert_summaries."""
    spreadsheet_name = kwargs.pop("spreadsheet_name", None)
    worksheet_name = kwargs.pop("worksheet_name", None)
    new_rows = kwargs.pop("new_rows", None)

    if args:
        first = args[0]
        remaining = list(args[1:])
        if isinstance(first, str) and (not new_rows or not isinstance(new_rows, list)):
            spreadsheet_name = spreadsheet_name or first
            if remaining:
                maybe_rows = remaining.pop(0)
                if isinstance(maybe_rows, list):
                    new_rows = maybe_rows
                else:
                    raise ValueError("Expected list of rows after spreadsheet name.")
        else:
            new_rows = first if isinstance(first, list) else new_rows

        # Allow optional worksheet name as next positional str
        if remaining:
            maybe_ws = remaining.pop(0)
            if isinstance(maybe_ws, str):
                worksheet_name = worksheet_name or maybe_ws

    if new_rows is None:
        raise ValueError("upsert_summaries requires a list of rows to write.")

    return new_rows, spreadsheet_name, worksheet_name


def _build_unique_key(row_id: Optional[str], email: Optional[str], source: Optional[str]) -> str:
    """Create a stable deduplication key for a sheet row."""
    row_id = (row_id or "").strip().lower()
    email = (email or "").strip().lower()
    source = (source or "").strip().lower()

    if row_id:
        return row_id
    if source and email:
        return f"{source}:{email}"
    return email

# ============================================================
# 100% IDEMPOTENT UPSERT FOR GOOGLE SHEETS
# ============================================================

def _stable_json(value):
    """Stable JSON encoding so dedupe works reliably."""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _row_equals(a: dict, b: dict) -> bool:
    """Check if two normalized rows are logically identical."""
    for col in HEADER:
        av = _stable_json(a.get(col, ""))
        bv = _stable_json(b.get(col, ""))
        if str(av) != str(bv):
            return False
    return True


def _should_update(existing: dict, incoming: dict) -> bool:
    """Decide whether this row needs an update."""
    # If summary changed → update
    if existing.get("contact_summary") != incoming.get("contact_summary"):
        return True

    # If role changed
    if str(existing.get("role")) != str(incoming.get("role")):
        return True

    # If role confidence changed
    if str(existing.get("role_confidence")) != str(incoming.get("role_confidence")):
        return True

    # If threads changed (compare JSON stable encoding)
    if _stable_json(existing.get("threads")) != _stable_json(incoming.get("threads")):
        return True

    return False


def upsert_summaries(*args, **kwargs):
    """
    IDEMPOTENT upsert for Google Sheets.
    Only writes to sheet when real changes occur.
    No duplicate rows. Stable keys. 
    """

    new_rows, spreadsheet_name, worksheet_name = _coerce_args(*args, **kwargs)

    if not isinstance(new_rows, list) or not new_rows:
        print("[Sheets] No rows to upsert.")
        return

    ws = _get_or_create_worksheet(spreadsheet_name, worksheet_name)

    # ------------------------------------------
    # Load existing rows and normalize
    # ------------------------------------------
    existing_lookup: dict[str, dict] = {}
    existing_records: List[Dict] = []

    try:
        existing_records = ws.get_all_records()
        for rec in existing_records:
            normalized = _normalize_row_payload(rec)
            key = _build_unique_key(
                normalized.get("id"),
                normalized.get("email"),
                normalized.get("source")
            )
            if key:
                existing_lookup[key] = normalized
    except Exception as e:
        print(f"[Sheets] Error reading sheet for dedupe: {e}")

    # ------------------------------------------
    # Merge incoming rows (idempotent logic)
    # ------------------------------------------
    inserts = 0
    updates = 0

    for row in new_rows:
        if not isinstance(row, dict):
            continue

        normalized = _normalize_row_payload(row)
        key = _build_unique_key(
            normalized.get("id"),
            normalized.get("email"),
            normalized.get("source")
        )
        if not key:
            continue

        if key not in existing_lookup:
            # New row → insert
            inserts += 1
            existing_lookup[key] = normalized
        else:
            # Existing row → check if update needed
            existing_row = existing_lookup[key]

            if _should_update(existing_row, normalized):
                updates += 1
                
                # Preserve last_summary unless content changed
                if existing_row.get("contact_summary") != normalized.get("contact_summary"):
                    # Summary changed → update timestamp
                    normalized["last_summary"] = datetime.now(timezone.utc).isoformat()
                else:
                    # No content change → keep old timestamp
                    normalized["last_summary"] = existing_row.get("last_summary")

                existing_lookup[key] = normalized

            # else: identical → do nothing

    # ------------------------------------------
    # If nothing changed, skip sheet write
    # ------------------------------------------
    if updates == 0 and inserts == 0:
        print("[Sheets] No changes — sheet sync skipped.")
        return

    # ------------------------------------------
    # Sort rows (latest first)
    # ------------------------------------------
    def _sort_key(item):
        dt = _parse_date(item.get("last_summary"))
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    ordered_rows = sorted(existing_lookup.values(), key=_sort_key, reverse=True)

    # ------------------------------------------
    # Prepare final write matrix
    # ------------------------------------------
    matrix = [HEADER]
    for row in ordered_rows:
        serialized = [_serialize_value(row.get(col, "")) for col in HEADER]
        matrix.append(serialized)

    extra_rows = max(0, len(existing_records) - len(ordered_rows))
    blank_row = [""] * len(HEADER)
    for _ in range(extra_rows):
        matrix.append(blank_row.copy())

    # ------------------------------------------
    # Write only when needed
    # ------------------------------------------
    try:
        ws.update("A1", matrix)
        print(
            f"[Sheets] ✅ Sync complete — "
            f"{updates} updated, {inserts} inserted, total {len(ordered_rows)} rows."
        )
    except Exception as e:
        print(f"[Sheets] ❌ Error rewriting sheet: {e}")
