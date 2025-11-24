from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
import asyncio
from datetime import datetime
from Summarizer.groq_summarizer import GroqSummarizer
from integrations.google_sheets import upsert_summaries
import os
from providers.mcp_summaries_provider import McpSummariesProvider
from integrations.google_sheets import read_all_summaries
import time
last_sync_time = 0
SYNC_INTERVAL = 300  # seconds (5 minutes)


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
    "Researcher": "tag-researcher",
    "Admin": "tag-admin",
    "Uncategorized": "tag-default",
}


class TimeoutError(Exception):
    pass


async def fetch_summaries_with_timeout(provider, limit: int, timeout_s: int = 30):
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, provider.get_summaries, limit), timeout=timeout_s)
    except asyncio.TimeoutError as e:
        raise TimeoutError("Summarization provider timed out") from e


async def fetch_and_merge_new_data_from_mcp(sheet_name="EmailAssistantSummaries", limit=50):
    """
    Fetch new summaries from MCP asynchronously, dedupe, and upsert only new summaries to Sheets.
    """
    global last_sync_time
    now = time.time()

    # ✅ Only fetch if enough time has passed
    if now - last_sync_time < SYNC_INTERVAL:
        print(f"[INFO] ⏳ Skipping fetch — last sync {round(now - last_sync_time, 1)}s ago (interval {SYNC_INTERVAL}s).")
        return

    print("[INFO] 🔄 Fetching new data from MCP...")

    last_sync_time = now
    mcp_rows = []  # ✅ always define early

    try:
        db = read_all_summaries(sheet_name)
        db_ids = set(row.get("id") for row in db if row.get("id"))

        provider = McpSummariesProvider()
        # use to_thread to avoid blocking event loop
        mcp_rows = await asyncio.to_thread(provider.get_summaries, limit)

    except Exception as e:
        print(f"[MCP] Error fetching summaries: {e}")
        return  # fail safely, don't crash background loop

    # ✅ Ensure valid format
    if not isinstance(mcp_rows, list):
        print("[MCP] unexpected mcp_rows format, expected list.")
        return

    # ✅ Ensure ids & timestamps exist
    for r in mcp_rows:
        if not r.get("id"):
            source = r.get("source", "gmail")
            r["id"] = f"{source}:{r.get('email','unknown')}"
        if not r.get("timestamp"):
            r["timestamp"] = datetime.utcnow().isoformat()

    # Process only new or updated rows
    new_rows = []
    for row in mcp_rows:
        row_id = row.get("id")
        if not row_id:
            continue
            
        # Check if we already have this in the database
        existing = next((r for r in db if r.get("id") == row_id), None)
        
        # Skip if we already have a summary and the content hasn't changed
        if existing and existing.get("summary") and not row.get("force_update", False):
            print(f"[MCP] Skipping already summarized: {row_id}")
            continue
            
        # Only summarize if we have thread bodies and no existing summary
        if row.get("_thread_bodies") and (not existing or not existing.get("summary")):
            try:
                source = row.get("source", "gmail")
                contact_email = row.get("email")
                summ = GroqSummarizer()
                summaries_texts = []
                
                for i, body in enumerate(row.get("_thread_bodies", [])):
                    if not body:
                        continue
                        
                    thread_id = (row.get("_thread_ids") or [None])[i] or f"{contact_email}_thread_{i}"
                    
                    # Check if we already have a cached summary
                    cached = summ._get_from_cache(source, contact_email, thread_id)
                    if cached and cached.get("summary"):
                        summaries_texts.append(cached["summary"])
                    else:
                        # Only summarize if we don't have a cached version
                        s = summ.summarize_text(body)
                        if s:
                            summaries_texts.append(s)
                            summ._set_cache(source, contact_email, thread_id, s)
                
                if summaries_texts:
                    row["summary"] = " ".join(summaries_texts)
                    
            except Exception as e:
                print(f"[MCP] Error summarizing {row_id}: {e}")
                row["summary"] = existing.get("summary", "") if existing else ""
        
        new_rows.append(row)

    if not new_rows:
        print("[Sheets] No new or updated summaries to process.")
        return

    # ✅ Push new rows to Google Sheets
    try:
        upsert_summaries(sheet_name, new_rows)
        print(f"[Sheets] ✅ Upserted {len(new_rows)} new summarized contacts.")
    except Exception as e:
        print(f"[Sheets] Error upserting summaries: {e}")


def format_pkt(date_str: str) -> str:
    """Convert ISO date or UNIX timestamp to 'DD Mon YYYY, hh:mm AM/PM (PKT)' on server."""
    from datetime import datetime, timezone, timedelta
    if not date_str:
        return ""
    try:
        # Handle UNIX timestamp
        if isinstance(date_str, (int, float)) or date_str.isdigit():
            d = datetime.fromtimestamp(float(date_str), tz=timezone.utc)
        else:
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
        return str(date_str)
    


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int = 20):
    # Kick off background sync; don't block first paint
    asyncio.create_task(fetch_and_merge_new_data_from_mcp(limit=limit))

    rows = read_all_summaries()  # Always display from sheets as the DB

    items = []
    for row in rows:
        email = row.get("email")
        if not email:
            continue

        summary_text = row.get("contact_summary") or row.get("summary") or ""
        date_value = row.get("last_summary") or row.get("timestamp") or row.get("date") or ""
        role_value = row.get("role") or row.get("Role") or "Uncategorized"
        importance_value = row.get("importance") or row.get("Importance") or ""

        item = {
            "id": row.get("id") or f"{row.get('source','unknown')}:{email}",
            "email": email,
            "role": role_value,
            "summary": summary_text,
            "date": format_pkt(date_value),
            "source": row.get("source", ""),
            "importance": importance_value,
            "role_class": ROLE_TO_CLASS.get(role_value, "tag-default"),
        }
        items.append(item)

    summary_count = len(items)
    unique_contacts = len({item["email"] for item in items})

    template = env.get_template("dashboard.html")
    html = template.render(items=items, summary_count=summary_count, unique_contacts=unique_contacts)
    return HTMLResponse(content=html)


@app.get("/api/summaries")
async def api_summaries(limit: int = 20):
    asyncio.create_task(fetch_and_merge_new_data_from_mcp(limit=limit))
    rows = read_all_summaries()

    items = []
    for row in rows:
        email = row.get("email")
        if not email:
            continue

        role_value = row.get("role") or row.get("Role") or "Uncategorized"
        summary_text = row.get("contact_summary") or row.get("summary") or ""
        date_value = row.get("last_summary") or row.get("timestamp") or row.get("date")

        items.append({
            "id": row.get("id") or f"{row.get('source','unknown')}:{email}",
            "email": email,
            "role": role_value,
            "summary": summary_text,
            "date": format_pkt(date_value),
            "source": row.get("source", ""),
            "role_class": ROLE_TO_CLASS.get(role_value, "tag-default"),
            "importance": row.get("importance") or row.get("Importance") or "",
        })

    return {"ok": True, "count": len(items), "items": items}
