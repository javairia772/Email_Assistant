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


def _get_client():
    creds = None
    credentials_file = os.getenv("GOOGLE_SHEETS_OAUTH_CLIENT", "credentials.json")
    token_file = os.getenv("GOOGLE_SHEETS_TOKEN", "token_gmail_sheets.pkl")
    
    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)
    # If credentials are not available or invalid, go through authorization flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=8081)
        # Save the credentials for the next run
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)
    return gspread.authorize(creds)


def _get_ws_with_header(sh, ws_name="Summaries"):
    # Guarantee worksheet exists with correct header, reset if broken
    correct_header = ["id", "email", "role", "summary", "date"]
    try:
        ws = sh.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ws_name, rows=100, cols=12)
        ws.append_row(correct_header)
        return ws
    # Read header row
    header = ws.row_values(1)
    # If header incorrect, reset sheet
    if [h.strip().lower() for h in header] != correct_header:
        print(f"[Sheets] Sheet header broken or missing, resetting to {correct_header}")
        sh.del_worksheet(ws)
        ws = sh.add_worksheet(title=ws_name, rows=100, cols=12)
        ws.append_row(correct_header)
    return ws


def read_all_summaries(sheet_name: str = "EmailAssistantSummaries") -> list[dict]:
    """
    Reads all summaries from the Google Sheet and returns a list of dicts.
    Assumes columns: id, email, role, summary, date
    """
    client = _get_client()
    try:
        sh = client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        print("[Sheets] Not found: {}".format(sheet_name))
        return []
    ws = _get_ws_with_header(sh)
    data = ws.get_all_records(default_blank='')
    # Filter ONLY correct keys
    OUT_KEYS = ["id", "email", "role", "summary", "date"]
    rows = []
    for d in data:
        filtered = {k: d.get(k, '') for k in OUT_KEYS}
        rows.append(filtered)
    print(f"[Sheets] Read {len(rows)} rows (showing up to 5):")
    import pprint
    pprint.pprint(rows[:5])
    return rows


def upsert_summaries(sheet_name: str, rows: List[Dict]):
    client = _get_client()
    try:
        sh = client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        sh = client.create(sheet_name)
    ws = _get_ws_with_header(sh)
    # Read all existing rows and aggregate as dict keyed by email
    OUT_KEYS = ["id", "email", "role", "summary", "date"]
    existing = ws.get_all_records(default_blank='')
    by_email = {}
    for row in existing:
        email = (row.get("email") or '').strip().lower()
        if not email:
            continue
        by_email[email] = {k: row.get(k, "") for k in OUT_KEYS}
    # Merge new rows by email
    for r in rows:
        email = (r.get("email") or '').strip().lower()
        if not email:
            continue
        # Always use the most up-to-date info from the latest MCP fetch
        by_email[email] = {k: r.get(k, '') for k in OUT_KEYS}
        by_email[email]["id"] = email
        by_email[email]["email"] = email
    # Rewrite everything (after header)
    ws.resize(rows=1) # keep only header row
    # Sheet order: id,email,role,summary,date
    allrows = [[rec[k] for k in OUT_KEYS] for rec in by_email.values()]
    if allrows:
        ws.append_rows(allrows, value_input_option="RAW")
    print(f"[Sheets] Upsert: wrote {len(allrows)} contacts (per-email deduped)")


