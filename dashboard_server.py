from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import json
from integrations.google_sheets import read_all_summaries
SUMMARY_CACHE_PATH = Path("Summaries/summaries_cache.json")


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
    

def _load_cached_summaries() -> dict:
    """Read the local summaries cache for contact drilldowns."""
    if not SUMMARY_CACHE_PATH.exists():
        return {}

    try:
        with SUMMARY_CACHE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"[Cache] Error reading {SUMMARY_CACHE_PATH}: {exc}")
        return {}

    summaries = data.get("summaries", data)
    if isinstance(summaries, dict):
        return summaries

    if isinstance(summaries, list):
        mapped = {}
        for entry in summaries:
            if not isinstance(entry, dict):
                continue
            key = entry.get("id") or f"{entry.get('source','')}:{entry.get('email','')}"
            if key:
                mapped[key] = entry
        return mapped

    return {}


def _parse_iso(value: str):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _build_detail_url(contact_id: str) -> str:
    return f"/contact/{quote(contact_id, safe='')}"


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int = 20):
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
        item["detail_url"] = _build_detail_url(item["id"])
        items.append(item)

    summary_count = len(items)
    unique_contacts = len({item["email"] for item in items})

    template = env.get_template("dashboard.html")
    html = template.render(items=items, summary_count=summary_count, unique_contacts=unique_contacts)
    return HTMLResponse(content=html)


@app.get("/api/summaries")
async def api_summaries(limit: int = 20):
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
            "detail_url": _build_detail_url(row.get("id") or f"{row.get('source','unknown')}:{email}"),
        })

    return {"ok": True, "count": len(items), "items": items}


@app.get("/contact/{contact_id}", response_class=HTMLResponse)
async def contact_detail(contact_id: str):
    summaries = _load_cached_summaries()
    contact_entry = summaries.get(contact_id)

    if not contact_entry:
        raise HTTPException(status_code=404, detail="Contact not found in cache.")

    email = contact_entry.get("email") or contact_id.split(":", 1)[-1]
    source = contact_entry.get("source", "")
    role = contact_entry.get("role", "Uncategorized")
    importance = contact_entry.get("importance") or ""
    top_summary = contact_entry.get("contact_summary") or contact_entry.get("summary") or ""
    last_summary = contact_entry.get("last_summary") or contact_entry.get("timestamp") or contact_entry.get("date") or ""

    threads = []
    for thread in contact_entry.get("threads", []):
        if not isinstance(thread, dict):
            continue
        ts = thread.get("timestamp") or thread.get("date") or thread.get("last_modified") or thread.get("created_at")
        threads.append({
            "id": thread.get("thread_id") or thread.get("id"),
            "subject": thread.get("subject") or "(No subject)",
            "summary": thread.get("summary") or thread.get("body") or thread.get("preview") or "",
            "importance": thread.get("importance") or "",
            "role": thread.get("role") or "",
            "timestamp": ts,
            "timestamp_display": format_pkt(ts),
        })

    threads.sort(key=lambda t: _parse_iso(t.get("timestamp")), reverse=True)

    template = env.get_template("contact_detail.html")
    html = template.render(
        contact={
            "id": contact_id,
            "email": email,
            "source": source,
            "role": role,
            "importance": importance,
            "summary": top_summary,
            "last_summary": format_pkt(last_summary),
            "detail_url": _build_detail_url(contact_id),
        },
        threads=threads,
    )
    return HTMLResponse(content=html)
