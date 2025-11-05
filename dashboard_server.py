import os
import asyncio
from collections import defaultdict, Counter
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from providers.mcp_summaries_provider import McpSummariesProvider
from integrations.google_sheets import upsert_summaries, read_all_summaries

# -----------------------
# FastAPI & Jinja setup
# -----------------------
app = FastAPI(title="Email Assistant Dashboard")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

app.mount("/static", StaticFiles(directory="static"), name="static")

ROLE_TO_CLASS = {
    "Student": "tag-student",
    "Faculty": "tag-faculty",
    "Vendor": "tag-vendor",
}

# -----------------------
# Exceptions
# -----------------------
class TimeoutError(Exception):
    pass

# -----------------------
# Helper functions
# -----------------------
async def fetch_summaries_with_timeout(provider, limit: int, timeout_s: int = 30):
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, provider.get_summaries, limit),
            timeout=timeout_s
        )
    except asyncio.TimeoutError as e:
        raise TimeoutError("Summarization provider timed out") from e

def fetch_and_merge_new_data_from_mcp(sheet_name="EmailAssistantSummaries", limit=50):
    """
    Fetch from MCP, dedupe, upsert only new summaries to Sheets.
    Runs synchronously; call it in a background task from routes.
    """
    # Read already existing IDs from the sheet
    db = read_all_summaries()
    db_ids = set(row.get("Id") for row in db)


    provider = McpSummariesProvider()
    mcp_rows = provider.get_summaries(limit)

    new_rows = [row for row in mcp_rows if row.get("id") not in db_ids]

    if new_rows:
        upsert_summaries(new_rows)

def format_pkt(date_str: str) -> str:
    """
    Convert ISO date to 'DD Mon YYYY, hh:mm AM/PM (PKT)' on server.
    """
    from datetime import datetime, timezone, timedelta

    if not date_str:
        return ""

    try:
        asISO = date_str if (date_str.endswith('Z') or ('+' in date_str)) else date_str + 'Z'
        d = datetime.fromisoformat(asISO.replace('Z', '+00:00'))
        pkt = d.astimezone(timezone.utc) + timedelta(hours=5)

        mo = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][pkt.month-1]
        day = f"{pkt.day:02d}"
        h24 = pkt.hour
        ampm = 'PM' if h24 >= 12 else 'AM'
        h12 = h24 % 12 or 12

        return f"{day} {mo} {pkt.year}, {h12:02d}:{pkt.minute:02d} {ampm} (PKT)"
    except Exception:
        return date_str

# -----------------------
# Routes
# -----------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int = 20):
    # Kick off background sync; don't block first paint
    asyncio.create_task(asyncio.to_thread(fetch_and_merge_new_data_from_mcp, limit=limit))

    rows = read_all_summaries()

    # Only valid rows
    valid = [
        it for it in rows
        if it.get("Id") and it.get("Email") and it.get("Summary") and it.get("Date")
    ]

    # Group by email
    by_email = defaultdict(list)
    for row in valid:
        by_email[row["Email"]].append(row)

    items = []
    for email, lst in by_email.items():
        summaries = "\n".join(x["Summary"] for x in lst if x.get("Summary"))
        dates = [x["Date"] for x in lst if x.get("Date")]
        date = max(dates) if dates else ""
        roles = [x.get("Role") for x in lst if x.get("Role")]
        role = Counter(roles).most_common(1)[0][0] if roles else ""

        items.append({
            "email": email,
            "role": role,
            "summary": summaries,
            "date": format_pkt(date),
        })

    for it in items:
        it["role_class"] = ROLE_TO_CLASS.get(it.get("role"), "tag-default")

    summary_count = sum(len(lst) for lst in by_email.values())
    unique_contacts = len(items)

    template = env.get_template("dashboard.html")
    html = template.render(
        items=items,
        summary_count=summary_count,
        unique_contacts=unique_contacts
    )
    return HTMLResponse(content=html)

@app.get("/api/summaries")
async def get_summaries(request: Request):
    """
    Fetch contact summaries from Google Sheets and return them in JSON format.
    Used by the dashboard frontend.
    """
    try:
        # Read summaries (list of dicts)
        rows = read_all_summaries()

        # Normalize/serialize records for frontend display
        formatted = []
        for r in rows:
            email = str(r.get("Email") or r.get("email") or "").strip()
            role = r.get("Role") or r.get("role") or "Student"
            summary = r.get("Summary") or r.get("summary") or "No summary available."
            date = r.get("Date") or r.get("date") or ""

            formatted.append({
                "email": email,
                "role": role,
                "summary": summary,
                "date": date,
            })

        print(f"[Dashboard] ✅ Returning {len(formatted)} summaries.")
        return JSONResponse(content=formatted, status_code=200)

    except Exception as e:
        print(f"[Dashboard] ❌ Error fetching summaries: {e}")
        return JSONResponse(
            content={"error": f"Failed to fetch summaries: {str(e)}"},
            status_code=500
        )


@app.get("/")
async def root():
    """Simple health check endpoint."""
    return {"status": "ok", "message": "Email Assistant Dashboard API running."}
