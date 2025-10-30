from typing import List, Dict, Optional
import os
import gspread
from google.oauth2.service_account import Credentials


SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Column headers in the sheet
HEADERS = ["Email", "Role", "Summary", "Date", "Thread IDs", "Message IDs"]

# Column indices (0-based)
COL_EMAIL = 0
COL_ROLE = 1
COL_SUMMARY = 2
COL_DATE = 3
COL_THREAD_IDS = 4
COL_MSG_IDS = 5


def _get_client():
    """Initialize and return gspread client."""
    keyfile = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "service_account.json")
    if not os.path.exists(keyfile):
        raise FileNotFoundError(f"Google Sheets service account file not found: {keyfile}")
    creds = Credentials.from_service_account_file(keyfile, scopes=SCOPE)
    return gspread.authorize(creds)


def _get_or_create_sheet(sheet_name: str = "EmailAssistantSummaries"):
    """Get existing sheet or create if it doesn't exist. Returns (spreadsheet, worksheet)."""
    client = _get_client()
    try:
        sh = client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        sh = client.create(sheet_name)

    try:
        ws = sh.worksheet("Summaries")
        # Check if headers exist
        if ws.row_values(1) != HEADERS:
            ws.insert_row(HEADERS, 1)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Summaries", rows=1000, cols=10)
        ws.append_row(HEADERS)

    return sh, ws


def _row_to_dict(row: List[str]) -> Dict:
    """Convert sheet row to dict. row[0] is email."""
    return {
        "email": row[COL_EMAIL] if len(row) > COL_EMAIL else "",
        "role": row[COL_ROLE] if len(row) > COL_ROLE else "",
        "summary": row[COL_SUMMARY] if len(row) > COL_SUMMARY else "",
        "date": row[COL_DATE] if len(row) > COL_DATE else "",
        "_thread_ids": row[COL_THREAD_IDS].split(",") if len(row) > COL_THREAD_IDS and row[COL_THREAD_IDS] else [],
        "_message_ids": row[COL_MSG_IDS].split(",") if len(row) > COL_MSG_IDS and row[COL_MSG_IDS] else [],
    }


def _dict_to_row(d: Dict) -> List[str]:
    """Convert dict to sheet row."""
    thread_ids_str = ",".join(d.get("_thread_ids", []))
    msg_ids_str = ",".join(d.get("_message_ids", []))
    return [
        d.get("email", ""),
        d.get("role", ""),
        d.get("summary", ""),
        d.get("date", ""),
        thread_ids_str,
        msg_ids_str,
    ]


def read_all_summaries(sheet_name: str = "EmailAssistantSummaries") -> List[Dict]:
    """Read all summaries from Google Sheets. Returns list of dicts."""
    _, ws = _get_or_create_sheet(sheet_name)
    all_rows = ws.get_all_values()
    if len(all_rows) <= 1:  # Only headers
        return []
    
    # Skip header row
    summaries = []
    for row in all_rows[1:]:
        if row[COL_EMAIL]:  # Only include rows with email
            summaries.append(_row_to_dict(row))
    
    return summaries


def get_summary_by_email(email: str, sheet_name: str = "EmailAssistantSummaries") -> Optional[Dict]:
    """Get summary for a specific email address. Returns None if not found."""
    _, ws = _get_or_create_sheet(sheet_name)
    all_rows = ws.get_all_values()
    
    if len(all_rows) <= 1:
        return None
    
    email_lower = email.lower()
    # Search from row 2 onwards (skip header)
    for idx, row in enumerate(all_rows[1:], start=2):
        if row[COL_EMAIL].lower() == email_lower:
            return _row_to_dict(row)
    
    return None


def upsert_summaries(rows: List[Dict], sheet_name: str = "EmailAssistantSummaries"):
    """
    Upsert summaries to Google Sheets. Updates existing rows by email, inserts new ones.
    rows: list of dicts with keys: email, role, summary, date, _thread_ids, _message_ids
    """
    _, ws = _get_or_create_sheet(sheet_name)
    all_rows = ws.get_all_values()
    
    # Build email -> row index map (excluding header)
    email_to_row: Dict[str, int] = {}
    if len(all_rows) > 1:
        for idx, row in enumerate(all_rows[1:], start=2):
            if row[COL_EMAIL]:
                email_to_row[row[COL_EMAIL].lower()] = idx
    
    updates = []  # (row_idx, new_row_data)
    new_rows = []
    
    for item in rows:
        email = item.get("email", "").lower()
        new_row = _dict_to_row(item)
        
        if email in email_to_row:
            # Update existing row
            updates.append((email_to_row[email], new_row))
        else:
            # New row to append
            new_rows.append(new_row)
    
    # Perform updates
    for row_idx, row_data in updates:
        ws.update(f"A{row_idx}:F{row_idx}", [row_data], value_input_option="RAW")
    
    # Append new rows
    if new_rows:
        ws.append_rows(new_rows, value_input_option="RAW")
    
    print(f"[Sheets] Upserted {len(updates)} updates, {len(new_rows)} inserts")


def clear_sheet(sheet_name: str = "EmailAssistantSummaries"):
    """Clear all data (keeps headers)."""
    _, ws = _get_or_create_sheet(sheet_name)
    ws.clear()
    ws.append_row(HEADERS)
    print(f"[Sheets] Cleared all data from {sheet_name}/Summaries")
