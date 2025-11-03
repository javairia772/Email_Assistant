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
        self.cache_path = Path("Summaries/summaries_cache.json")

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
    def _summarize_contact_threads(self, contact: Dict) -> str:
        """Generate a concise summary for a contact using their message bodies."""
        all_texts = []

        # Combine Outlook previews and Gmail bodies
        for t in contact.get("threads", []):
            if "preview" in t:
                text = t["preview"]
            elif "messages" in t:
                text = "\n".join(m.get("body", "") for m in t["messages"])
            else:
                text = ""
            
            if text:
                # Strip HTML if any
                if "<" in text and ">" in text:
                    try:
                        text = BeautifulSoup(text, "html.parser").get_text(separator="\n")
                    except Exception:
                        text = re.sub(r"<[^>]+>", "", text)
                
                # Normalize whitespace
                text = re.sub(r"\s+", " ", text).strip()

                # Truncate if too long (e.g., >2000 chars)
                if len(text) > 2000:
                    text = text[:2000] + "..."

                all_texts.append(text)

        combined_text = "\n\n".join(all_texts).strip()
        if not combined_text:
            return "No message content available."

        try:
            summary = self.summarizer.summarize_text(combined_text)
            # Clean final summary whitespace
            return re.sub(r"\s+", " ", summary).strip()
        except Exception as e:
            print(f"[MCP] Summarization error for {contact.get('email')}: {e}")
            return "Summary generation failed."

    # -----------------------------------------------------------------
    # MERGED SUMMARIES + CACHE
    # -----------------------------------------------------------------
    def get_summaries(self, limit=10) -> List[Dict]:
        print("[INFO] Fetching summaries from Gmail + Outlook...")

        gmail_data = self._from_gmail(limit)
        outlook_data = self._from_outlook(limit)

        all_data = gmail_data + outlook_data
        print(f"[INFO] ✅ Total summaries fetched: {len(all_data)}")

        # Generate AI summaries
        for contact in all_data:
            # Ensure stable id and timestamp for dedupe & merging
            source = contact.get("source", "gmail")
            email = contact.get("email") or "unknown"
            contact["id"] = f"{source}:{email}"
            # Add timestamp if not present
            contact["timestamp"] = contact.get("timestamp") or datetime.utcnow().isoformat()

            contact["summary"] = self._summarize_contact_threads(contact)

        # --- Cache logic ---
        try:
            old_cache = []
            if self.cache_path.exists():
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    try:
                        old_cache = json.load(f)
                    except Exception:
                        print("[CACHE] invalid json in cache, overwriting.")

            # old_cache should be a list; normalize
            if isinstance(old_cache, dict):
                # convert to list of values if dict keyed format was used previously
                old_cache_list = list(old_cache.values())
            else:
                old_cache_list = old_cache or []

            # Merge by (email, source)
            unique_map = {(x.get("email"), x.get("source")): x for x in old_cache_list if isinstance(x, dict)}
            for d in all_data:
                unique_map[(d.get("email"), d.get("source"))] = d

            merged_list = list(unique_map.values())

            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(merged_list, f, indent=2, ensure_ascii=False)

            print(f"[CACHE] ✅ Updated {self.cache_path} with {len(merged_list)} records")

        except Exception as e:
            print(f"[CACHE ERROR] {e}")

        return all_data
