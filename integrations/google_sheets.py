from typing import List, Dict
import os
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


# ---------------------- AUTH ----------------------
def _get_client():
    creds = None
    credentials_file = os.getenv("GOOGLE_SHEETS_OAUTH_CLIENT", "credentials.json")
    token_file = os.getenv("GOOGLE_SHEETS_TOKEN", "token_gmail_sheets.pkl")

    print(f"[Sheets] Using credentials file: {credentials_file}")
    print(f"[Sheets] Using spreadsheet: {SPREADSHEET_NAME}")
    print(f"[Sheets] Using worksheet: {WORKSHEET_NAME}")

    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=8081)
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)

    return gspread.authorize(creds)


# ---------------------- SPREADSHEET HELPERS ----------------------
def _get_or_create_spreadsheet(gc):
    """Get or create spreadsheet."""
    try:
        for sh in gc.openall():
            if sh.title == SPREADSHEET_NAME:
                return sh
    except Exception:
        pass

    print(f"[Sheets] Creating new spreadsheet: {SPREADSHEET_NAME}")
    return gc.create(SPREADSHEET_NAME)


def _get_or_create_worksheet():
    """Safely get worksheet — never resets data."""
    try:
        gc = _get_client()
        sh = _get_or_create_spreadsheet(gc)
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
            print(f"[Sheets] Found worksheet: {WORKSHEET_NAME}")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=100, cols=len(HEADER))
            ws.append_row(HEADER)
            print(f"[Sheets] Created new worksheet: {WORKSHEET_NAME}")
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

    print(f"[WARN] Could not parse date: {date_str}")
    return None


# ---------------------- READ SHEET ----------------------
def read_all_summaries() -> list[dict]:
    """Read all rows safely from Google Sheets."""
    try:
        ws = _get_or_create_worksheet()
        
        # First, get all values to inspect the headers
        all_values = ws.get_all_values()
        if not all_values:
            return []
            
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
            
        print(f"[Sheets] ✅ Read {len(rows)} rows (showing up to 5):")
        import pprint; pprint.pprint(rows[:5])
        return rows
        
    except Exception as e:
        print(f"[Sheets] ❌ Error reading sheet: {str(e)}")
        return []


# ---------------------- UPSERT (ADD/UPDATE) ----------------------
def _merge_summary(old_text: str, new_text: str) -> str:
    """Prefer meaningful summaries over placeholders."""
    placeholder_phrases = ["Summary of", "not available yet"]
    if new_text and not any(p in new_text for p in placeholder_phrases):
        return new_text.strip()
    if old_text and not any(p in old_text for p in placeholder_phrases):
        return old_text.strip()
    return new_text.strip() or old_text.strip()


def upsert_summaries(new_rows: List[Dict]):
    """
    Safe upsert (update or insert) for Google Sheets.
    - Never clears or resets data.
    - Updates by matching email field.
    """
    if not new_rows:
        print("[Sheets] No rows to upsert.")
        return

    ws = _get_or_create_worksheet()

    # Read existing data
    try:
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            existing_rows = []
            email_to_row = {}
        else:
            header = [h.lower() for h in all_values[0]]
            existing_rows = all_values[1:]
            email_col_idx = header.index('email') if 'email' in header else 0
            email_to_row = {
                str(row[email_col_idx]).strip().lower(): i + 2
                for i, row in enumerate(existing_rows)
                if len(row) > email_col_idx and row[email_col_idx].strip()
            }
    except Exception as e:
        print(f"[Sheets] Error reading sheet: {e}")
        existing_rows = []
        email_to_row = {}

    updates = []
    new_rows_to_append = []

    for new_row in new_rows:
        email = str(new_row.get('email', '')).strip().lower()
        if not email:
            continue

        # Ensure order of columns matches header
        row_data = []
        for col in HEADER:
            value = new_row.get(col, '')
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            row_data.append(str(value) if value is not None else '')

        if email in email_to_row:
            row_num = email_to_row[email]
            updates.append({
                'range': f'A{row_num}:{chr(65 + len(HEADER) - 1)}{row_num}',
                'values': [row_data]
            })
        else:
            new_rows_to_append.append(row_data)

    # Apply batch updates
    if updates:
        try:
            ws.batch_update(updates)
            print(f"[Sheets] ✅ Updated {len(updates)} existing rows.")
        except Exception as e:
            print(f"[Sheets] ❌ Error updating rows: {e}")

    # Append new rows safely
    if new_rows_to_append:
        try:
            ws.append_rows(new_rows_to_append)
            print(f"[Sheets] ✅ Appended {len(new_rows_to_append)} new rows.")
        except Exception as e:
            print(f"[Sheets] ❌ Error appending rows: {e}")

    print(f"[Sheets] ✅ Sync complete — {len(updates)} updated, {len(new_rows_to_append)} added.")
