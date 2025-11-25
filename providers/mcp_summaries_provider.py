from typing import List, Dict
from datetime import datetime, timezone
import json, os, re, time
from pathlib import Path
# Imports
from Summarizer.groq_summarizer import GroqSummarizer
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector

import re
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


    # -----------------------------------------------------------------
    # OUTLOOK EMAILS
    # -----------------------------------------------------------------
    def _from_outlook(self, limit: int):
        contacts_by_email = {}
        outlook = OutlookConnector()

        try:
            messages = outlook.list_messages(limit)
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
                    "subject": subject,
                    "preview": body_text.strip()
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
        gmail = GmailConnector()

        try:
            threads = gmail.list_threads(limit)
            for t in threads:
                tid = t.get("id")
                if not tid:
                    continue

                thread_messages = gmail.get_message(tid)
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

                contacts_by_email[contact_email]["threads"].append({
                    "id": tid,
                    "messages": clean_messages
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

        # Generate contact-level summary object
        contact_entry = self.summarizer.summarize_contact_threads(
            all_threads_texts,
            source=contact.get("source"),
            contact_email=contact.get("email"),
            thread_ids=thread_ids
        )

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
            if cache_key in existing_summaries:
                existing_contact = existing_summaries[cache_key]
                existing_thread_ids = {t.get("id") for t in existing_contact.get("threads", [])}
                new_thread_ids = {t.get("id") for t in contact.get("threads", [])}
                
                # If no new threads, reuse cached summary
                if new_thread_ids.issubset(existing_thread_ids):
                    print(f"⚡ Using cached summary for {contact_email} (no new threads)")
                    merged_summaries.append(existing_contact)
                    continue
                else:
                    print(f"🔄 Found new threads for {contact_email}, re-summarizing...")
            
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
