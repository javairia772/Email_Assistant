from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
import asyncio

import os
from providers.mcp_summaries_provider import McpSummariesProvider
from integrations.google_sheets import upsert_summaries, read_all_summaries


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


class TimeoutError(Exception):
    pass


async def fetch_summaries_with_timeout(provider, limit: int, timeout_s: int = 30):
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, provider.get_summaries, limit), timeout=timeout_s)
    except asyncio.TimeoutError as e:
        raise TimeoutError("Summarization provider timed out") from e


def fetch_and_merge_new_data_from_mcp(sheet_name="EmailAssistantSummaries", limit=50):
    """
    Fetch from MCP, dedupe, upsert only new summaries to Sheets.
    """
    # Read already existing IDs from the sheet
    db = read_all_summaries(sheet_name)
    db_ids = set(row.get("id") for row in db)
    provider = McpSummariesProvider()
    mcp_rows = provider.get_summaries(limit)
    new_rows = [row for row in mcp_rows if row.get("id") not in db_ids]
    if new_rows:
        upsert_summaries(sheet_name, new_rows)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int = 20):
    # Always try to merge new data before loading view
    fetch_and_merge_new_data_from_mcp(limit=limit)
    import collections
    from datetime import datetime
    rows = read_all_summaries()
    # Only valid rows
    valid = [
        it for it in rows
        if it.get("id") and it.get("email") and it.get("summary") and it.get("date")
    ]
    # Group by email
    by_email = collections.defaultdict(list)
    for row in valid:
        by_email[row["email"]].append(row)
    items = []
    for email, lst in by_email.items():
        # Concatenate all summaries, most recent date, most common or first role
        summaries = "\n".join(x["summary"] for x in lst if x.get("summary"))
        dates = [x["date"] for x in lst if x.get("date")]
        # Get the most recent date in ISO format
        try:
            date = max(dates, key=lambda d: datetime.fromisoformat(d.replace('Z','+00:00')))
        except:
            date = dates[0] if dates else ""
        roles = [x.get("role") for x in lst if x.get("role")]
        # Most common role or first
        role = collections.Counter(roles).most_common(1)[0][0] if roles else ""
        items.append({
            "email": email,
            "role": role,
            "summary": summaries,
            "date": date,
        })
    print(f"[Dashboard] Rendering {len(items)} contacts (unique emails). Sample:")
    import pprint
    pprint.pprint(items[:5])
    for it in items:
        it["role_class"] = ROLE_TO_CLASS.get(it.get("role"), "tag-default")
    summary_count = sum(len(lst) for lst in by_email.values())
    unique_contacts = len(items)
    template = env.get_template("dashboard.html")
    html = template.render(items=items, summary_count=summary_count, unique_contacts=unique_contacts)
    return HTMLResponse(content=html)


@app.get("/api/summaries")
async def api_summaries(limit: int = 20):
    fetch_and_merge_new_data_from_mcp(limit=limit)
    items = read_all_summaries()[:limit]
    for it in items:
        it["role_class"] = ROLE_TO_CLASS.get(it.get("role"), "tag-default")
    return {"ok": True, "count": len(items), "items": items}


