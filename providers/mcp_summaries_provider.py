from typing import List, Dict
from datetime import datetime, timezone
import json, os, re, time
from pathlib import Path
from email.utils import parsedate_to_datetime
from Summarizer.groq_summarizer import GroqSummarizer
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from Agents.agent_tools import AgentTools
from classifier.email_classifier import classify_email
from bs4 import BeautifulSoup

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
    def __init__(self):
        self.summarizer = GroqSummarizer()
        self.cache_path = Path(__file__).resolve().parent / "Summaries" / "summaries_cache.json"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.gmail = GmailConnector()
        self.outlook = OutlookConnector()
        self.agent_tools = AgentTools()
        self.reply_log_path = Path(__file__).resolve().parent / "Summaries" / "auto_replies.json"
        self.auto_replied_threads = self._load_reply_log()

    def _load_reply_log(self) -> Dict:
        if self.reply_log_path.exists():
            try:
                with self.reply_log_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_reply_log(self):
        self.reply_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.reply_log_path.open("w", encoding="utf-8") as f:
            json.dump(self.auto_replied_threads, f, indent=2, ensure_ascii=False)

    def _normalize_timestamp(self, value: str) -> str:
        if not value:
            return datetime.now(timezone.utc).isoformat()
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            try:
                parsed = _parse_iso(value)
                return parsed.isoformat()
            except Exception:
                return datetime.now(timezone.utc).isoformat()

    def _threads_changed(self, contact: Dict, existing_contact: Dict) -> bool:
        if not existing_contact:
            return True
        existing_threads = {
            t.get("id"): t.get("last_message_ts") or t.get("timestamp")
            for t in existing_contact.get("threads", [])
        }
        for thread in contact.get("threads", []):
            tid = thread.get("id")
            new_ts = thread.get("last_message_ts")
            if tid not in existing_threads:
                return True
            old_ts = existing_threads.get(tid)
            if new_ts and old_ts and new_ts > old_ts:
                return True
        return False

    def _handle_high_priority_reply(self, source: str, contact_email: str, thread_data: Dict, latest_msg: Dict, summary: str) -> bool:
        thread_id = thread_data.get("id")
        if not thread_id:
            return False
        signature = f"{source}:{thread_id}"
        last_ts = thread_data.get("last_message_ts") or self._normalize_timestamp(latest_msg.get("date", ""))
        already_replied_ts = self.auto_replied_threads.get(signature)
        if already_replied_ts and last_ts and already_replied_ts >= last_ts:
            return False

        reply = self.agent_tools.generate_reply(
            email_id=thread_id,
            sender=contact_email,
            subject=latest_msg.get("subject", thread_data.get("last_subject", "")),
            body=latest_msg.get("body", thread_data.get("last_body", "")),
            summary=summary,
        )
        if not reply.get("success"):
            return False

        reply_text = reply.get("reply", "")
        try:
            if source == "gmail":
                self.gmail.send_reply(
                    thread_id=thread_id,
                    to_email=contact_email,
                    subject=latest_msg.get("subject", thread_data.get("last_subject", "")),
                    reply_body=reply_text,
                )
            else:
                self.outlook.send_reply(
                    message_id=thread_data.get("last_message_id"),
                    to_email=contact_email,
                    subject=latest_msg.get("subject", thread_data.get("last_subject", "")),
                    reply_body=reply_text,
                )
            self.auto_replied_threads[signature] = last_ts or datetime.now(timezone.utc).isoformat()
            self._save_reply_log()
            return True
        except Exception as exc:
            print(f"[AutoReply] Failed to send reply for {thread_id}: {exc}")
            return False


    # -----------------------------------------------------------------
    # OUTLOOK EMAILS
    # -----------------------------------------------------------------
    def _from_outlook(self, limit: int):
        contacts_by_email = {}

        try:
            messages = self.outlook.list_messages(limit)
            print("[DEBUG] Outlook messages sample:", messages[:2])

            for msg in messages:
                # skip anything that's not a dict
                if not isinstance(msg, dict):
                    print("[WARN] Skipping malformed Outlook message:", msg)
                    continue

                # --- Sender ---
                sender = (
                    msg.get("sender")
                    if isinstance(msg.get("sender"), str) else
                    msg.get("sender", {}).get("emailAddress", {}).get("address")
                ) or (
                    msg.get("from", {}).get("emailAddress", {}).get("address")
                    if isinstance(msg.get("from"), dict) else msg.get("from")
                ) or "unknown@outlook.com"

                # --- Subject ---
                subject = msg.get("subject", "")

                # --- Body / preview ---
                body_html = msg.get("body") or msg.get("bodyPreview") or ""
                
                # Strip HTML tags for readable preview
                if "<" in body_html and ">" in body_html:
                    try:
                        # BeautifulSoup method (robust)
                        from bs4 import BeautifulSoup
                        body_text = BeautifulSoup(body_html, "html.parser").get_text(separator="\n")
                    except Exception:
                        # Fallback regex (simple)
                        body_text = re.sub(r"<[^>]+>", "", body_html)
                else:
                    body_text = body_html

                msg_id = msg.get("id")

                # --- Build contact grouping ---
                if sender not in contacts_by_email:
                    contacts_by_email[sender] = {
                        "email": sender,
                        "threads": [],
                        "source": "outlook"
                    }

                contacts_by_email[sender]["threads"].append({
                    "id": msg_id,
                    "messages": [{
                        "sender": sender,
                        "subject": subject,
                        "body": body_text.strip(),
                        "date": msg.get("receivedDateTime", ""),
                        "message_id": msg_id
                    }],
                    "last_message_ts": self._normalize_timestamp(msg.get("receivedDateTime", "")),
                    "last_message_id": msg_id,
                    "last_subject": subject,
                    "last_body": body_text.strip()
                })

            return list(contacts_by_email.values())

        except Exception as e:
            print(f"[MCP] Outlook error: {e}")
            return []



    # -----------------------------------------------------------------
    # GMAIL EMAILS
    # -----------------------------------------------------------------
    def _from_gmail(self, limit: int) -> List[Dict]:
        contacts_by_email = {}

        try:
            threads = self.gmail.list_threads(limit)
            for t in threads:
                tid = t.get("id")
                if not tid:
                    continue

                thread_messages = self.gmail.get_message(tid)
                if not isinstance(thread_messages, list):
                    print(f"[WARN] Thread {tid} messages not a list, skipping...")
                    continue

                # Find sender email
                contact_email = "unknown@gmail.com"
                for msg in thread_messages:
                    if not isinstance(msg, dict):
                        print(f"[WARN] Skipping malformed message: {msg}")
                        continue
                    sender = msg.get("sender", "")
                    if sender and "@" in sender:
                        contact_email = sender
                        break

                if contact_email not in contacts_by_email:
                    contacts_by_email[contact_email] = {
                        "email": contact_email,
                        "threads": [],
                        "source": "gmail"
                    }

                # Clean message bodies
                clean_messages = []
                for msg in thread_messages:
                    if not isinstance(msg, dict):
                        continue
                    body = msg.get("body", "")
                    # Strip HTML if present
                    if "<" in body and ">" in body:
                        try:
                            body = BeautifulSoup(body, "html.parser").get_text(separator="\n")
                        except Exception:
                            body = re.sub(r"<[^>]+>", "", body)
                    body = re.sub(r"\s+", " ", body).strip()
                    clean_messages.append({**msg, "body": body})

                last_msg = clean_messages[-1] if clean_messages else {}
                last_ts = self._normalize_timestamp(last_msg.get("date", ""))

                contacts_by_email[contact_email]["threads"].append({
                    "id": tid,
                    "messages": clean_messages,
                    "last_message_ts": last_ts,
                    "last_message_id": last_msg.get("message_id"),
                    "last_subject": last_msg.get("subject", ""),
                    "last_body": last_msg.get("body", "")
                })

            return list(contacts_by_email.values())

        except Exception as e:
            print(f"[MCP] Gmail error: {e}")
            return []

    # -----------------------------------------------------------------
    # SUMMARIZATION
    # -----------------------------------------------------------------
    def _summarize_contact_threads(self, contact: Dict) -> Dict:
        """Summarize all threads for a contact using GroqSummarizer, includes role/importance."""
        thread_ids = []
        all_threads_texts = []
        thread_details = {}

        for t in contact.get("threads", []):
            thread_id = t.get("id")
            thread_ids.append(thread_id)

            # Build thread message list for summarizer
            if "messages" in t:
                thread_emails = t["messages"]
            else:
                thread_emails = [{"sender": contact["email"], "subject": t.get("subject", ""), "body": t.get("preview", "")}]

            # Summarize each thread (also caches role/importance)
            summary = self.summarizer.summarize_thread(
                thread_emails,
                source=contact.get("source"),
                contact_email=contact.get("email"),
                thread_id=thread_id
            )

            # Append text for contact-level summary
            all_threads_texts.append(summary)

            latest_msg = thread_emails[-1] if thread_emails else {}
            classification = classify_email(
                latest_msg.get("sender", contact.get("email")),
                latest_msg.get("subject", ""),
                latest_msg.get("body", "")
            )
            last_ts = t.get("last_message_ts") or self._normalize_timestamp(latest_msg.get("date", ""))
            signature = f"{contact.get('source')}:{thread_id}"
            auto_replied = False
            previous_reply_ts = self.auto_replied_threads.get(signature)
            if previous_reply_ts and last_ts and previous_reply_ts >= last_ts:
                auto_replied = True
            if classification.get("importance", "").lower() == "high":
                auto_replied = self._handle_high_priority_reply(
                    contact.get("source"),
                    contact.get("email"),
                    t,
                    latest_msg,
                    summary
                )
            thread_details[thread_id] = {
                "importance": classification.get("importance"),
                "importance_confidence": classification.get("importance_confidence"),
                "role": classification.get("role"),
                "role_confidence": classification.get("role_confidence"),
                "last_message_ts": last_ts,
                "auto_replied": auto_replied,
                "last_message_id": t.get("last_message_id"),
                "last_subject": t.get("last_subject"),
                "last_body": t.get("last_body"),
            }

        # Generate contact-level summary object
        contact_entry = self.summarizer.summarize_contact_threads(
            all_threads_texts,
            source=contact.get("source"),
            contact_email=contact.get("email"),
            thread_ids=thread_ids
        )

        for thread_meta in contact_entry.get("threads", []):
            tid = thread_meta.get("id")
            details = thread_details.get(tid, {})
            thread_meta["importance"] = details.get("importance", thread_meta.get("importance"))
            thread_meta["importance_confidence"] = details.get("importance_confidence", thread_meta.get("importance_confidence"))
            thread_meta["role"] = details.get("role", thread_meta.get("role"))
            thread_meta["role_confidence"] = details.get("role_confidence", thread_meta.get("role_confidence"))
            thread_meta["last_message_ts"] = details.get("last_message_ts")
            thread_meta["auto_replied"] = details.get("auto_replied", False)
            thread_meta["last_message_id"] = details.get("last_message_id")
            thread_meta["last_subject"] = details.get("last_subject")
            thread_meta["last_body"] = details.get("last_body")

        return contact_entry
    # -----------------------------------------------------------------
    # MERGED SUMMARIES + CACHE
    # -----------------------------------------------------------------
    def get_summaries(self, limit=10, existing_cache=None) -> List[Dict]:
        """
        Fetch and summarize emails from Gmail + Outlook.
        
        Args:
            limit: Number of emails to fetch per source
            existing_cache: Previously loaded cache to avoid re-summarizing
        
        Returns:
            List of contact summaries
        """
        print("[INFO] Fetching summaries from Gmail + Outlook...")

        gmail_data = self._from_gmail(limit)
        outlook_data = self._from_outlook(limit)
        all_data = gmail_data + outlook_data
        print(f"[INFO] ✅ Total contacts fetched: {len(all_data)}")

        merged_summaries = []
        
        # Load existing cache if provided
        existing_summaries = {}
        if existing_cache and "summaries" in existing_cache:
            existing_summaries = existing_cache["summaries"]

        # Summarize each contact
        for contact in all_data:
            contact_email = contact.get("email")
            source = contact.get("source")
            cache_key = f"{source}:{contact_email}"
            
            # ✅ Check if this contact is already in cache
            existing_contact = existing_summaries.get(cache_key)
            if existing_contact and not self._threads_changed(contact, existing_contact):
                print(f"⚡ Using cached summary for {contact_email} (no updates)")
                merged_summaries.append(existing_contact)
                continue
            else:
                if existing_contact:
                    print(f"🔄 Changes detected for {contact_email}, re-summarizing...")
            
            # Summarize contact (new or updated)
            contact_summary = self._summarize_contact_threads(contact)
            merged_summaries.append(contact_summary)

        # --- Build final cache JSON ---
        cache_data = {
            "seen": {
                "gmail": [c["id"] for c in merged_summaries if c.get("source") == "gmail"],
                "outlook": [c["id"] for c in merged_summaries if c.get("source") == "outlook"]
            },
            "summaries": merged_summaries,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

        # Write cache
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            print(f"[CACHE] ✅ Saved structured cache with {len(merged_summaries)} summaries to {self.cache_path}")
        except Exception as e:
            print(f"[CACHE ERROR] {e}")

        return merged_summaries
