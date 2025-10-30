from typing import List, Dict
from datetime import datetime, timezone

# Import MCP tool functions. These are defined and registered in main_mcp.py
# Importing them here lets us reuse the same implementations the MCP server exposes.
from main_mcp import (
    gmail_list_threads_raw,
    gmail_get_message_raw,
    outlook_list_messages_raw,
)


def _infer_role_from_email(email_addr: str) -> str:
    e = (email_addr or "").lower()
    if e.endswith(".edu") or "university" in e:
        return "Faculty"
    if e.endswith(".io") or e.endswith(".inc") or e.endswith(".co"):
        return "Vendor"
    return "Student"


def _parse_iso(s: str) -> datetime:
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


class McpSummariesProvider:
    def _from_outlook(self, limit: int) -> List[Dict]:
        contacts_by_email: Dict[str, Dict] = {}
        try:
            msgs = outlook_list_messages_raw(top=limit * 2)
        except Exception as e:
            print(f"[MCP] Outlook error: {e}")
            return []

        for m in msgs:
            email_only = m.get("from", "")
            date_str = m.get("receivedDateTime", "")
            msg_id = m.get("id", "")
            date_obj = _parse_iso(date_str)
            email_lower = email_only.lower()
            role = _infer_role_from_email(email_only)

            c = contacts_by_email.get(email_lower)
            if not c:
                contacts_by_email[email_lower] = {
                    "email": email_only,
                    "role": role,
                    "_message_ids": [msg_id] if msg_id else [],
                    "date": date_str,
                }
            else:
                if msg_id and msg_id not in c.get("_message_ids", []):
                    c.setdefault("_message_ids", []).append(msg_id)
                if date_obj > _parse_iso(c.get("date", "")):
                    c["date"] = date_str

        items: List[Dict] = []
        for c in contacts_by_email.values():
            cnt = len(c.get("_message_ids", []))
            c["summary"] = f"Summary of {cnt} Outlook message(s) not available yet." if cnt else "Summary not available yet."
            items.append(c)
        return items

    def _from_gmail(self, limit: int) -> List[Dict]:
        contacts_by_email: Dict[str, Dict] = {}
        try:
            threads = gmail_list_threads_raw(max_results=limit * 2)
        except Exception as e:
            print(f"[MCP] Gmail error listing threads: {e}")
            return []

        for t in threads:
            tid = t.get("id")
            if not tid:
                continue
            try:
                thread = gmail_get_message_raw(tid)
            except Exception as e:
                print(f"[MCP] Gmail error get_message: {e}")
                continue
            messages = thread.get("messages", [])
            if not messages:
                continue
            headers = messages[0].get("payload", {}).get("headers", [])
            header_dict = {h["name"]: h["value"] for h in headers}
            sender = header_dict.get("From", "")
            date_raw = header_dict.get("Date", "")
            try:
                date_obj = datetime.strptime(date_raw[:25], "%a, %d %b %Y %H:%M:%S")
                date_str = date_obj.replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                date_str = ""

            import re
            email_only = sender
            m = re.match(r"(.*)<(.+@.+)>", sender)
            if m:
                email_only = m.group(2).strip()

            email_lower = email_only.lower()
            role = _infer_role_from_email(email_only)

            c = contacts_by_email.get(email_lower)
            if not c:
                contacts_by_email[email_lower] = {
                    "email": email_only,
                    "role": role,
                    "_thread_ids": [tid],
                    "date": date_str,
                }
            else:
                if tid not in c.get("_thread_ids", []):
                    c.setdefault("_thread_ids", []).append(tid)
                if _parse_iso(date_str) > _parse_iso(c.get("date", "")):
                    c["date"] = date_str

        items: List[Dict] = []
        for c in contacts_by_email.values():
            cnt = len(c.get("_thread_ids", []))
            c["summary"] = f"Summary of {cnt} Gmail thread(s) not available yet." if cnt else "Summary not available yet."
            items.append(c)
        return items

    def get_summaries(self, limit: int = 20) -> List[Dict]:
        half = max(1, limit // 2)
        data: List[Dict] = []
        outlook_items = self._from_outlook(half)
        gmail_items = self._from_gmail(limit - len(outlook_items))
        data.extend(outlook_items)
        data.extend(gmail_items)

        # Merge duplicates across sources
        merged: Dict[str, Dict] = {}
        for item in data:
            email = item.get("email", "").lower()
            if email not in merged:
                merged[email] = item
            else:
                existing = merged[email]
                # merge IDs
                if item.get("_thread_ids"):
                    existing["_thread_ids"] = existing.get("_thread_ids", []) + item.get("_thread_ids", [])
                if item.get("_message_ids"):
                    existing["_message_ids"] = existing.get("_message_ids", []) + item.get("_message_ids", [])
                # newer date wins
                if _parse_iso(item.get("date", "")) > _parse_iso(existing.get("date", "")):
                    existing["date"] = item.get("date", "")

        result = list(merged.values())
        for r in result:
            t = len(r.get("_thread_ids", []))
            m = len(r.get("_message_ids", []))
            parts = []
            if t:
                parts.append(f"{t} Gmail thread(s)")
            if m:
                parts.append(f"{m} Outlook message(s)")
            r["summary"] = f"Summary of {', '.join(parts)} not available yet." if parts else "Summary not available yet."

        result.sort(key=lambda x: _parse_iso(x.get("date", "")), reverse=True)
        return result[:limit]


