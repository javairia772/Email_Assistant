from typing import List, Dict
import os
import gspread
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_NAME = "EmailAssistantSummaries"   # consistent name
WORKSHEET_NAME = "Summaries"                   # consistent sheet tab
HEADER = ["Id", "Email", "Role", "Summary", "Date"]
OUT_KEYS = HEADER.copy()

def normalize_summary_item(item: dict) -> dict:
    """Ensure all summary records have required fields."""
    return {
        "Id": item.get("Id", ""),
        "Email": item.get("Email", ""),
        "Role": item.get("Role", ""),
        "Summary": item.get("Summary", ""),
        "Date": item.get("Date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # "source": item.get("source", ""),
    }

# ------------------------- AUTH CLIENT -------------------------
def _get_client():
    creds = None
    credentials_file = os.getenv("GOOGLE_SHEETS_OAUTH_CLIENT", "credentials.json")
    token_file = os.getenv("GOOGLE_SHEETS_TOKEN", "token_gmail_sheets.pkl")

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


# ---------------------- WORKSHEET HANDLER ----------------------
def _get_or_create_worksheet():
    client = _get_client()

    # Open or create spreadsheet
    try:
        sh = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = client.create(SPREADSHEET_NAME)
        print(f"[Sheets] Created spreadsheet '{SPREADSHEET_NAME}'")

    # Try to get worksheet or create if missing
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=100, cols=len(HEADER))
        ws.append_row(HEADER)
        print(f"[Sheets] Created worksheet '{WORKSHEET_NAME}' with header.")

    # Validate header row (case-insensitive)
    try:
        header = [h.strip().lower() for h in ws.row_values(1)]
    except Exception:
        header = []

    expected = [h.lower() for h in HEADER]
    if header != expected:
        print(f"[Sheets] Header mismatch detected — fixing in place.")
        ws.clear()
        ws.append_row(HEADER)

    return ws


# ------------------------- READ DATA -------------------------
def read_all_summaries() -> list[dict]:
    """Read all summaries safely."""
    ws = _get_or_create_worksheet()
    data = ws.get_all_records(default_blank='')
    rows = [{k: d.get(k, '') for k in HEADER} for d in data]
    print(f"[Sheets] Read {len(rows)} rows (showing up to 5):")
    import pprint; pprint.pprint(rows[:5])
    return rows


# ------------------------- UPSERT DATA -------------------------
def _merge_summary(old_text: str, new_text: str) -> str:
    placeholder_phrases = ["Summary of", "not available yet"]
    if new_text and not any(p in new_text for p in placeholder_phrases):
        return new_text.strip()
    if old_text and not any(p in old_text for p in placeholder_phrases):
        return old_text.strip()
    return new_text.strip() or old_text.strip()


def upsert_summaries(new_rows: List[Dict]):
    if not new_rows:
        print("[Sheets] No rows to upsert.")
        return

    ws = _get_or_create_worksheet()
    existing = ws.get_all_records(default_blank='')

    by_email = {
        str(r.get("Email", "")).strip().lower(): r for r in existing if r.get("Email")
    }

    for new in new_rows:
        normalized = normalize_summary_item(new)
        email = str(normalized["Email"]).strip().lower()
        if not email:
            continue
        by_email[email] = normalized

    merged_rows = list(by_email.values())
    if not merged_rows:
        print("[Sheets] ⚠️ Merged rows empty — aborting update.")
        return  # ✅ safeguard against clearing everything

    ws.clear()
    ws.append_row(HEADER)
    ws.append_rows(
        [[r.get(k, "") for k in HEADER] for r in merged_rows],
        value_input_option="RAW"
    )
    print(f"[Sheets] ✅ Upsert successful: wrote {len(merged_rows)} rows.")