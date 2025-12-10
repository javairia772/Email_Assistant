from typing import Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
import json
from integrations.google_sheets import read_all_summaries
from Summarizer.groq_summarizer import GroqSummarizer
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from providers.reply_queue import ReplyQueue
from providers.sent_store import SentStore
from providers.utils import extract_email, normalize_contact_id, expand_possible_ids
SUMMARY_CACHE_PATH = Path("Summaries/summaries_cache.json")


app = FastAPI(title="Email Assistant Dashboard")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

app.mount("/static", StaticFiles(directory="static"), name="static")
reply_queue = ReplyQueue()
sent_store = SentStore()
gmail_client = GmailConnector()
outlook_client = OutlookConnector()
groq_client = GroqSummarizer()


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
    mapped = {}
    iterable = []
    if isinstance(summaries, dict):
        iterable = summaries.values()
    elif isinstance(summaries, list):
        iterable = summaries
    else:
        return {}

    for entry in iterable:
        if not isinstance(entry, dict):
            continue
        email = extract_email(entry.get("email", ""))
        source_guess = entry.get("source") or (
            "gmail"
            if "gmail" in (entry.get("id") or "").lower()
            else "outlook"
            if "outlook" in (entry.get("id") or "").lower()
            else ""
        )
        norm_id = normalize_contact_id(entry.get("id") or f"{source_guess}:{email}")
        if not norm_id:
            continue
        entry["id"] = norm_id
        entry["email"] = email or entry.get("email", "")
        mapped[norm_id] = entry
    return mapped

def _parse_iso(value: str):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _build_detail_url(contact_id: str) -> str:
    return f"/contact/{quote(contact_id, safe='')}"


def _latest_thread_ts(threads_value):
    """
    Extract the latest timestamp from a threads field that may be a list or JSON string.
    """
    if not threads_value:
        return ""
    threads = threads_value
    if isinstance(threads_value, str):
        try:
            import json as _json
            threads = _json.loads(threads_value)
        except Exception:
            return ""
    if not isinstance(threads, list):
        return ""
    latest = ""
    for t in threads:
        if not isinstance(t, dict):
            continue
        ts = t.get("last_message_ts") or t.get("timestamp") or t.get("date") or t.get("last_modified") or t.get("created_at")
        if not ts:
            continue
        if not latest or _parse_iso(ts) > _parse_iso(latest):
            latest = ts
    return latest


def _find_contact_entry(contact_id: str, summaries: dict) -> Dict:
    """Central helper to resolve a contact entry with flexible ID matching."""
    norm_id = normalize_contact_id(contact_id)
    contact_entry = summaries.get(norm_id) or summaries.get(contact_id)

    if not contact_entry:
        for pid in expand_possible_ids(contact_id):
            if pid in summaries:
                return summaries[pid]

    if contact_entry:
        return contact_entry
    raise HTTPException(status_code=404, detail="Contact not found in cache.")


def _format_thread_messages(messages: list, contact_email: str) -> list:
    """Normalize message payloads for the chat view."""
    contact_email = (contact_email or "").lower()
    if not isinstance(messages, list):
        return []

    def _format_date(value):
        try:
            # Try to parse RFC2822 style first
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(value)
            return dt.astimezone(timezone.utc)
        except Exception:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                return None

    normalized = []
    for msg in messages or []:
        sender_raw = msg.get("sender") or msg.get("from", "")
        sender_email = extract_email(sender_raw).lower()
        ts = _format_date(msg.get("date", "") or msg.get("receivedDateTime", ""))
        normalized.append({
            "sender": sender_raw,
            "subject": msg.get("subject", ""),
            "body": msg.get("body", ""),
            "date": ts.isoformat() if ts else msg.get("date", "") or "",
            "display_ts": format_pkt(ts.isoformat()) if ts else (msg.get("date", "") or ""),
            "is_outgoing": sender_email and sender_email != contact_email,
        })

    normalized.sort(key=lambda m: _parse_iso(m.get("date", "")))
    return normalized


def _decorate_draft(draft: Dict) -> Dict:
    return {
        "id": draft.get("id"),
        "thread_id": draft.get("thread_id"),
        "subject": draft.get("subject") or "(No subject)",
        "reply": draft.get("generated_reply", ""),
        "prompt": draft.get("prompt", ""),
        "importance": draft.get("importance", ""),
        "role": draft.get("role", ""),
        "status": draft.get("status", "pending_review"),
        "created_at": draft.get("created_at"),
        "created_at_display": format_pkt(draft.get("created_at")),
        "updated_at_display": format_pkt(draft.get("updated_at")),
        "history": draft.get("history", []),
        "last_message_ts": draft.get("last_message_ts"),
    }


def _send_email(source: str, thread_id: str, contact_email: str, subject: str, reply_text: str, message_id: str = None):
    """Send an email reply, maintaining thread context.
    
    Args:
        source: The email source ('gmail' or 'outlook')
        thread_id: The ID of the conversation thread
        contact_email: The email address to send to
        subject: The email subject
        reply_text: The body of the reply
        message_id: The ID of the message being replied to (for threading)
    """
    source_lower = (source or "").lower()
    
    # Format message_id for Gmail if needed
    if source_lower == "gmail" and message_id:
        # Ensure message_id is properly formatted with angle brackets if it's not already
        if not message_id.startswith('<'):
            message_id = f'<{message_id}'
        if not message_id.endswith('>'):
            message_id = f'{message_id}>'
    
    try:
        if source_lower == "gmail":
            gmail_client.send_reply(
                thread_id=thread_id,
                to_email=contact_email,
                subject=subject,
                reply_body=reply_text,
                in_reply_to=message_id,
                references=message_id  # For Gmail, we can use the same message ID for both
            )
        elif source_lower == "outlook":
            outlook_client.send_reply(
                message_id=message_id,
                to_email=contact_email,
                subject=subject,
                reply_body=reply_text,
                thread_id=thread_id  # Pass thread_id for logging purposes
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source for sending reply: {source}")
    except Exception as e:
        print(f"[ERROR] Failed to send email via {source_lower}: {str(e)}")
        raise


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int = 20):
    rows = read_all_summaries()  # Always display from sheets as the DB

    items = []
    for row in rows:
        email = row.get("email")
        if not email:
            continue

        summary_text = row.get("contact_summary") or row.get("summary") or ""
        date_value = _latest_thread_ts(row.get("threads")) or row.get("last_summary") or row.get("timestamp") or row.get("date") or ""
        role_value = row.get("role") or row.get("Role") or "Uncategorized"

        parsed_ts = _parse_iso(_latest_thread_ts(row.get("threads")) or row.get("last_summary") or row.get("timestamp") or row.get("date") or "")
        item = {
            "id": row.get("id") or f"{row.get('source','unknown')}:{email}",
            "email": email,
            "role": role_value,
            "summary": summary_text,
            "date": format_pkt(date_value),
            "source": row.get("source", ""),
            "role_class": ROLE_TO_CLASS.get(role_value, "tag-default"),
            "sort_ts": parsed_ts,
        }
        item["detail_url"] = _build_detail_url(item["id"])
        items.append(item)

    items.sort(key=lambda it: it.get("sort_ts", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    for it in items:
        it.pop("sort_ts", None)

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
        date_value = _latest_thread_ts(row.get("threads")) or row.get("last_summary") or row.get("timestamp") or row.get("date")

        parsed_ts = _parse_iso(_latest_thread_ts(row.get("threads")) or row.get("last_summary") or row.get("timestamp") or row.get("date") or "")
        items.append({
            "id": row.get("id") or f"{row.get('source','unknown')}:{email}",
            "email": email,
            "role": role_value,
            "summary": summary_text,
            "date": format_pkt(date_value),
            "source": row.get("source", ""),
            "role_class": ROLE_TO_CLASS.get(role_value, "tag-default"),
            "importance": "",
            "detail_url": _build_detail_url(row.get("id") or f"{row.get('source','unknown')}:{email}"),
            "sort_ts": parsed_ts,
        })

    items.sort(key=lambda it: it.get("sort_ts", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    for it in items:
        it.pop("sort_ts", None)
    return {"ok": True, "count": len(items), "items": items}


@app.get("/contact/{contact_id}", response_class=HTMLResponse)
async def contact_detail(contact_id: str):
    summaries = _load_cached_summaries()
    # Try normalized key and fallbacks
    norm_id = normalize_contact_id(contact_id)
    contact_entry = summaries.get(norm_id) or summaries.get(contact_id)

    if not contact_entry:
        for pid in expand_possible_ids(contact_id):
            if pid in summaries:
                contact_entry = summaries[pid]
                contact_id = pid
                break

    if not contact_entry:
        raise HTTPException(status_code=404, detail="Contact not found in cache.")

    email = contact_entry.get("email") or contact_id.split(":", 1)[-1]
    source = contact_entry.get("source", "")
    role = contact_entry.get("role", "Uncategorized")
    importance = contact_entry.get("importance") or ""
    top_summary = contact_entry.get("contact_summary") or contact_entry.get("summary") or ""
    last_summary = contact_entry.get("last_summary") or contact_entry.get("timestamp") or contact_entry.get("date") or ""

    # Merge threads from the contact entry with any raw threads present in the cache file
    threads = []
    # Load raw cache to ensure we include any previously-stored threads
    raw_threads = []
    try:
        if SUMMARY_CACHE_PATH.exists():
            with SUMMARY_CACHE_PATH.open("r", encoding="utf-8") as f:
                raw_cache = json.load(f)
            raw_summaries = raw_cache.get("summaries", raw_cache)
            # Try match by normalized id, or by source:email key
            raw_entry = None
            # direct id match
            raw_entry = raw_summaries.get(contact_entry.get("id")) if isinstance(raw_summaries, dict) else None
            if not raw_entry:
                # try source:email key
                key = f"{contact_entry.get('source')}:{contact_entry.get('email')}"
                raw_entry = raw_summaries.get(key) if isinstance(raw_summaries, dict) else None
            if raw_entry and isinstance(raw_entry.get("threads"), list):
                raw_threads = [t for t in raw_entry.get("threads") if isinstance(t, dict)]
    except Exception:
        raw_threads = []

    # Build a dict of threads by id, preferring the most recent info from contact_entry
    threads_by_id = {}
    def _add_thread_obj(t):
        if not isinstance(t, dict):
            return
        tid = t.get("thread_id") or t.get("id")
        if not tid:
            return
        threads_by_id[str(tid)] = t

    for t in raw_threads:
        _add_thread_obj(t)
    for t in contact_entry.get("threads", []):
        _add_thread_obj(t)

    for tid, thread in threads_by_id.items():
        ts = thread.get("last_message_ts") or thread.get("timestamp") or thread.get("date") or thread.get("last_modified") or thread.get("created_at")
        threads.append({
            "id": tid,
            "subject": thread.get("subject") or "(No subject)",
            "summary": thread.get("summary") or thread.get("body") or thread.get("preview") or "",
            "importance": thread.get("importance") or "",
            "role": thread.get("role") or "",
            "timestamp": ts,
            "timestamp_display": format_pkt(ts),
            "detail_url": f"/contact/{quote(contact_id, safe='')}/thread/{quote(tid or '', safe='')}" if tid else None,
        })

    threads.sort(key=lambda t: _parse_iso(t.get("timestamp")), reverse=True)

    possible_ids = expand_possible_ids(contact_id)
    drafts = []
    for pid in possible_ids:
        drafts.extend(reply_queue.list_drafts(contact_id=pid))
    if not drafts:
        alt_id = contact_entry.get("id") or f"{source}:{email}"
        if alt_id and alt_id != contact_id:
            drafts = reply_queue.list_drafts(contact_id=alt_id)
        elif source and email and ":" not in contact_id:
            drafts = reply_queue.list_drafts(contact_id=f"{source}:{email}")
    pending_drafts = [_decorate_draft(d) for d in drafts if d.get("status") == "pending_review"]
    history_drafts = [_decorate_draft(d) for d in drafts if d.get("status") != "pending_review"]

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
        pending_drafts=pending_drafts,
        history_drafts=history_drafts,
    )
    return HTMLResponse(content=html)


@app.get("/contact/{contact_id}/thread/{thread_id}", response_class=HTMLResponse)
async def thread_detail(contact_id: str, thread_id: str):
    summaries = _load_cached_summaries()
    contact_entry = _find_contact_entry(contact_id, summaries)

    contact_email = contact_entry.get("email") or contact_id.split(":", 1)[-1]
    source = (contact_entry.get("source") or "").lower() or "gmail"

    # Pull thread metadata from cached threads
    thread_meta = next(
        (t for t in contact_entry.get("threads", []) if (t.get("thread_id") or t.get("id")) == thread_id),
        {}
    )
    subject = thread_meta.get("subject") or "(No subject)"

    # Fetch full messages for chat-style view
    messages = []
    try:
        if source == "gmail":
            messages = gmail_client.fetch_threads_by_id(thread_id)
        elif source == "outlook":
            messages = outlook_client.fetch_thread_by_id(contact_email, thread_id)
    except Exception as exc:
        print(f"[ThreadDetail] Failed to load thread {thread_id}: {exc}")
        messages = []

    normalized_messages = _format_thread_messages(messages, contact_email)

    template = env.get_template("thread_detail.html")
    html = template.render(
        contact={
            "id": contact_id,
            "email": contact_email,
            "source": source,
            "detail_url": _build_detail_url(contact_id),
        },
        thread={
            "id": thread_id,
            "subject": subject,
        },
        messages=normalized_messages,
    )
    return HTMLResponse(content=html)


@app.post("/api/generate-reply")
async def generate_reply(
    contact_id: str = Body(...),
    thread_id: str = Body(...),
    user_prompt: str = Body(...)
):
    """Generate a reply for a thread using thread summary + user prompt."""
    try:
        from urllib.parse import unquote
        
        # Decode URL-encoded contact_id
        decoded_contact_id = unquote(contact_id)
        
        summaries = _load_cached_summaries()
        
        # First try with the exact ID from the URL
        contact_entry = summaries.get(decoded_contact_id)
        
        # If not found, try to find a matching contact by normalizing the ID
        if not contact_entry and ':' in decoded_contact_id:
            source_part, email_part = decoded_contact_id.split(':', 1)
            
            # Try different variations of the contact ID
            variations = [
                decoded_contact_id,  # Original format
                f"{source_part}:{email_part.split('<')[0].strip()}",  # Without angle brackets
                f"{source_part}:{email_part.split('<')[-1].split('>')[0].strip()}"  # Just email part
            ]
            
            # Try each variation until we find a match
            for variation in variations:
                contact_entry = summaries.get(variation)
                if contact_entry:
                    break
        
        # As a last resort, try to find by email only (without source prefix)
        if not contact_entry and ':' in decoded_contact_id:
            _, email_part = decoded_contact_id.split(':', 1)
            # Extract just the email if it's in <email> format
            if '<' in email_part and '>' in email_part:
                email = email_part.split('<')[-1].split('>')[0].strip()
            else:
                email = email_part.strip()
                
            # Search through all summaries for a matching email
            for key, entry in summaries.items():
                entry_email = None
                # Extract email from the key if it's in the format "source:name <email>"
                if ':' in key and '<' in key and '>' in key:
                    entry_email = key.split('<')[-1].split('>')[0].strip()
                # Or if it's just "source:email"
                elif ':' in key and '@' in key.split(':')[1]:
                    entry_email = key.split(':', 1)[1].strip()
                
                # Check if emails match
                if entry_email and entry_email.lower() == email.lower():
                    contact_entry = entry
                    break
        
        if not contact_entry:
            raise HTTPException(status_code=404, detail=f"Contact not found: {decoded_contact_id}")
        
        # Find the thread
        thread = None
        for t in contact_entry.get("threads", []):
            if (t.get("thread_id") or t.get("id")) == thread_id:
                thread = t
                break
        
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        thread_summary = thread.get("summary") or thread.get("body") or ""
        if not thread_summary:
            raise HTTPException(status_code=400, detail="Thread summary not available")
        
        prompt = f"""You are an email assistant helping write a professional reply.

Thread Summary:
{thread_summary}

User Instructions:
{user_prompt}

Generate a concise, professional reply based on the thread summary and user instructions. 
Write the reply directly (no greetings like "Here's a reply:")."""
        
        reply_text = groq_client._run_groq_model(prompt)
        
        return {
            "ok": True,
            "reply": reply_text,
            "thread_id": thread_id,
            "contact_id": contact_id
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/drafts/save")
async def save_draft(
    draft_id: str = Body(...),
    reply_text: str = Body(...)
):
    draft = reply_queue.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    reply_queue.update_draft(
        draft_id,
        generated_reply=reply_text,
        history={
            "event": "edited",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Draft edited via dashboard",
        },
    )
    print(f"[DraftQueue] ✏️ Draft {draft_id} updated")
    return {"ok": True, "draft": _decorate_draft(reply_queue.get_draft(draft_id))}


@app.post("/api/drafts/reject")
async def reject_draft(draft_id: str = Body(...), reason: str = Body(default="Rejected by reviewer")):
    draft = reply_queue.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    reply_queue.update_draft(
        draft_id,
        status="rejected",
        history={
            "event": "rejected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": reason,
        },
    )
    print(f"[DraftQueue] ❌ Draft {draft_id} rejected")
    return {"ok": True}


@app.post("/api/drafts/send")
async def send_draft(draft_id: str = Body(...)):
    draft = reply_queue.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    reply_text = draft.get("generated_reply", "").strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Draft reply text is empty")

    _send_email(
        draft.get("source"),
        draft.get("thread_id"),
        draft.get("contact_email"),
        draft.get("subject") or "(no subject)",
        reply_text,
        message_id=draft.get("last_message_id"),
    )
    reply_queue.update_draft(
        draft_id,
        status="sent",
        history={
            "event": "sent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Draft sent after human approval",
        },
        sent_at=datetime.now(timezone.utc).isoformat(),
    )
    print(f"[DraftQueue] ✅ Draft {draft_id} sent")
    return {"ok": True}


@app.post("/api/send-reply")
async def send_reply(
    contact_id: str = Body(...),
    thread_id: str = Body(...),
    reply_text: str = Body(...),
    subject: str = Body(...),
    draft_id: str = Body(default=None)
):
    """Send a reply to a thread via Gmail or Outlook."""
    try:
        from urllib.parse import unquote
        
        # Decode URL-encoded contact_id
        decoded_contact_id = unquote(contact_id)
        
        summaries = _load_cached_summaries()
        
        # First try with the exact ID from the URL
        contact_entry = summaries.get(decoded_contact_id)
        
        # If not found, try to find a matching contact by normalizing the ID
        if not contact_entry and ':' in decoded_contact_id:
            source_part, email_part = decoded_contact_id.split(':', 1)
            
            # Try different variations of the contact ID
            variations = [
                decoded_contact_id,  # Original format
                f"{source_part}:{email_part.split('<')[0].strip()}",  # Without angle brackets
                f"{source_part}:{email_part.split('<')[-1].split('>')[0].strip()}"  # Just email part
            ]
            
            # Try each variation until we find a match
            for variation in variations:
                contact_entry = summaries.get(variation)
                if contact_entry:
                    break
        
        # As a last resort, try to find by email only (without source prefix)
        if not contact_entry and ':' in decoded_contact_id:
            _, email_part = decoded_contact_id.split(':', 1)
            # Extract just the email if it's in <email> format
            if '<' in email_part and '>' in email_part:
                email = email_part.split('<')[-1].split('>')[0].strip()
            else:
                email = email_part.strip()
                
            # Search through all summaries for a matching email
            for key, entry in summaries.items():
                entry_email = None
                # Extract email from the key if it's in the format "source:name <email>"
                if ':' in key and '<' in key and '>' in key:
                    entry_email = key.split('<')[-1].split('>')[0].strip()
                # Or if it's just "source:email"
                elif ':' in key and '@' in key.split(':')[1]:
                    entry_email = key.split(':', 1)[1].strip()
                
                # Check if emails match
                if entry_email and entry_email.lower() == email.lower():
                    contact_entry = entry
                    break
        
        if not contact_entry:
            raise HTTPException(status_code=404, detail=f"Contact not found: {decoded_contact_id}")
        
        source = contact_entry.get("source", "").lower()
        contact_email = contact_entry.get("email")
        
        # Find the thread and get the last message ID for threading
        thread = None
        message_id = None
        
        # First try to find the thread in the contact's threads
        for t in contact_entry.get("threads", []):
            if (t.get("thread_id") or t.get("id")) == thread_id:
                thread = t
                # Try to get the message ID from different possible fields
                message_id = t.get("last_message_id") or t.get("message_id") or t.get("id")
                break
        
        # If we still don't have a message ID, try to get it from the thread details
        if not message_id and source_lower == "gmail":
            try:
                # Fetch the thread to get the latest message ID
                thread_details = gmail_client.service.users().threads().get(
                    userId="me", id=thread_id
                ).execute()
                if thread_details and 'messages' in thread_details and thread_details['messages']:
                    # Get the ID of the most recent message in the thread
                    message_id = thread_details['messages'][-1]['id']
            except Exception as e:
                print(f"[ERROR] Failed to fetch thread details: {str(e)}")
        
        print(f"[DEBUG] Sending reply with thread_id={thread_id}, message_id={message_id}")
        _send_email(source, thread_id, contact_email, subject, reply_text, message_id=message_id)

        if draft_id:
            note = "Sent via manual review"
            reply_queue.update_draft(
                draft_id,
                status="sent",
                generated_reply=reply_text,
                history={"event": "sent", "timestamp": datetime.now(timezone.utc).isoformat(), "note": note},
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
            print(f"[DraftQueue] 📬 Draft {draft_id} sent and marked as completed.")

        return {
            "ok": True,
            "message": "Reply sent successfully",
            "thread_id": thread_id
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Compose / send ad-hoc email (also used by external MCP tool triggers)
@app.post("/api/compose-email")
async def compose_email(
    to: str = Body(...),
    subject: str = Body(...),
    body: str = Body(...),
    attachments: list = Body(default=None),
    source: str = Body(default="gmail"),
):
    try:
        src = (source or "gmail").lower()
        if src == "gmail":
            GmailConnector().send_email(to, subject, body, attachments or [])
        elif src == "outlook":
            OutlookConnector().send_email(to, subject, body, attachments or [])
        else:
            raise HTTPException(status_code=400, detail="Unsupported source")
        sent_store.record(to, subject, body, source=src)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/sent", response_class=HTMLResponse)
async def sent_view():
    sent_items = sent_store.list_sent()
    template = env.get_template("sent.html")
    html = template.render(items=sent_items)
    return HTMLResponse(content=html)


@app.get("/api/sent")
async def api_sent(limit: int = 200):
    items = sent_store.list_sent(limit=limit)
    return {"ok": True, "count": len(items), "items": items}
