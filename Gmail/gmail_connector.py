# Gmail/gmail_connector.py
from Gmail.gmail_auth import GmailAuth
import base64
from email.mime.text import MIMEText
from googleapiclient.errors import HttpError
from email.header import decode_header
import re
import json
from pathlib import Path
from datetime import datetime, timezone
# Import summarization logic (Groq + caching)
from Summarizer.summarize_helper import summarize_thread_logic , summarize_contact_logic


class GmailConnector:
    def __init__(self):
        self.auth = GmailAuth()
        self.service = self.auth.authenticate()

    # ------------------------------------------------------
    # List threads
    # ------------------------------------------------------
    def list_threads(self, max_results=5):
        """List recent Gmail threads with sender & subject metadata."""
        try:
            results = self.service.users().threads().list(userId="me", maxResults=max_results).execute()
            threads = results.get("threads", [])
            enriched_threads = []

            for t in threads:
                thread_id = t["id"]

                # Fetch one thread to get sender & subject (cheap lightweight call)
                thread = self.service.users().threads().get(userId="me", id=thread_id).execute()
                messages = thread.get("messages", [])
                if not messages:
                    continue

                # Get most recent message
                last_msg = messages[-1]
                headers = {h["name"]: h["value"] for h in last_msg["payload"].get("headers", [])}

                sender = headers.get("From", "unknown")
                subject = headers.get("Subject", "(no subject)")
                snippet = thread.get("snippet", "")

                enriched_threads.append({
                    "id": thread_id,
                    "sender": sender,
                    "subject": subject,
                    "snippet": snippet,
                    "threadId": thread_id,  # for summarizer compatibility
                })

            return enriched_threads

        except HttpError as e:
            print(f"[GmailConnector] Gmail API error: {e}")
            return []


    # ------------------------------------------------------
    # Get a full thread
    # ------------------------------------------------------
    def get_message(self, thread_id):
        """Get details for a specific thread."""
        try:
            thread = self.service.users().threads().get(userId="me", id=thread_id).execute()
            # Normalize messages so summarizer never sees plain strings
            parsed_messages = self._parse_thread(thread)
            return parsed_messages
        except HttpError as e:
            return {"error": f"Gmail API error: {e}"}

    # ------------------------------------------------------
    # NEW: Fetch all threads for a contact (for summarizing)
    # ------------------------------------------------------
    def fetch_threads(self, contact_email, max_results=10, top=None, auto=True):        
        """
        Fetch all threads that include a given contact email.
        If auto=False, skip auto-summarization to avoid recursion.
        """
        if top and not max_results:
            max_results = top  # ensure both styles work
        try:
            query = f"from:{contact_email} OR to:{contact_email}"
            results = self.service.users().threads().list(
                userId="me", q=query, maxResults=max_results
            ).execute()

            threads = results.get("threads", [])
            all_threads = []
            seen_threads = set()

            for t in threads:
                thread_id = t["id"]
                if thread_id in seen_threads:
                    continue
                seen_threads.add(thread_id)

                full_thread = self.service.users().threads().get(
                    userId="me", id=thread_id
                ).execute()

                parsed = self._parse_thread(full_thread)
                all_threads.append(parsed)

                # 🔥 Only auto-summarize when not called recursively
                if auto:
                    self._auto_summarize_thread(contact_email, thread_id, full_thread)

            # ✅ After all threads fetched, summarize contact once (only if auto=True)
            if auto:
                from Summarizer.summarize_helper import summarize_contact_logic
                summarize_contact_logic("gmail", contact_email, lambda e: self.fetch_threads(e, auto=False),
                                        top=50, force_refresh=False)

            return all_threads

        except HttpError as e:
            return {"error": f"Gmail API error: {e}"}

    # ------------------------------------------------------
    # AUTO-SUMMARIZATION TRIGGER (New)
    # ------------------------------------------------------
    def _auto_summarize_thread(self, contact_email, thread_id, thread_obj):
        print(f"[DEBUG] Auto-summarizing for {contact_email} — thread {thread_id}")
        try:
            parsed_messages = self._parse_thread(thread_obj)
            clean_parts = []
            for m in parsed_messages:
                body = m['body'].replace("\r", " ").replace("\n", " ").strip()
                clean_parts.append(f"From: {m['sender']}\nSubject: {m['subject']}\nDate: {m['date']}\n\n{body}\n")
            email_body = "\n---\n".join(clean_parts)
            
            print("[DEBUG] Cleaned email text (first 300 chars):", email_body[:300].replace("\n", " "))
            summarize_thread_logic("gmail", contact_email, thread_id, text=email_body, force=True)

        except Exception as e:
            print(f"[AutoSummarize] Failed for {contact_email} thread {thread_id}: {e}")



    # ------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------
    def _extract_body(self, payload):
        """Recursively extract plain text or HTML body from Gmail payloads."""
        if not payload:
            return ""

        body_data = ""
        mime_type = payload.get("mimeType", "")
        body = payload.get("body", {})

        # ✅ Try to extract plain text first
        if mime_type == "text/plain" and body.get("data"):
            return self._decode_base64(body["data"])

        # ✅ If only HTML is available, fall back to it
        elif mime_type == "text/html" and body.get("data"):
            import re
            html = self._decode_base64(body["data"])
            # Convert basic HTML to text (strip tags)
            text = re.sub(r"<[^>]+>", "", html)
            return text

        # ✅ Recurse into multipart
        if "parts" in payload:
            for part in payload["parts"]:
                text = self._extract_body(part)
                if text:
                    return text

        return ""


    def _parse_thread(self, thread):
        messages = thread.get("messages", [])
        parsed = []
        for msg in messages:
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

            sender = headers.get("From", "")
            subject = headers.get("Subject", "")
            date = headers.get("Date", "")
            message_id = msg.get("id", "")  # Get the message ID from the Gmail API response

            body = self._extract_body(msg["payload"])  # ✅ use recursive extractor

            parsed.append({
                "sender": sender,
                "subject": subject,
                "body": body.strip(),
                "date": date,
                "message_id": message_id  # Include message_id in the parsed output
            })
        return parsed


    def _decode_base64(self, data):
        """Safely decode Gmail's base64 body."""
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("UTF-8")
        except Exception:
            return ""

    # ------------------------------------------------------
    # Optional: plain text joiner for summarization
    # ------------------------------------------------------
    def get_thread_text(self, thread_id):
        """Return a thread’s combined text for summarization."""
        messages = self.get_message(thread_id)
        if isinstance(messages, dict) and "error" in messages:
            return messages["error"]

        combined = []
        for msg in messages:
            combined.append(
                f"From: {msg['sender']}\nSubject: {msg['subject']}\n\n{msg['body']}\n"
            )
        return "\n---\n".join(combined)

    def fetch_threads_by_id(self, thread_id):
        """
        Return a parsed Gmail thread as list[dict] for summarization.
        Each dict contains sender, subject, body, date.
        """
        try:
            thread = self.service.users().threads().get(userId="me", id=thread_id).execute()
            parsed_messages = self._parse_thread(thread)
            return parsed_messages
        except HttpError as e:
            return {"error": f"Gmail API error: {e}"}


    # ------------------------------------------------------
    # SEND REPLY
    # ------------------------------------------------------
    def send_reply(self, thread_id, to_email, subject, reply_body, in_reply_to=None, references=None):
        """Send a reply within an existing Gmail thread.
        
        Args:
            thread_id: The ID of the thread to reply to
            to_email: Email address to send the reply to
            subject: Subject of the email (will be prefixed with 'Re: ')
            reply_body: The body of the reply
            in_reply_to: The Message-ID of the message being replied to (optional)
            references: References header for threading (optional)
        """
        # Get the sender's email address from Gmail settings
        profile = self.service.users().getProfile(userId='me').execute()
        sender_email = profile.get('emailAddress')
        
        message = MIMEText(reply_body)
        message["to"] = to_email
        message["from"] = sender_email  # Explicitly set the From header
        message["subject"] = f"Re: {subject}" if not subject.lower().startswith("re: ") else subject
        
        # Add threading headers if available
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = references or in_reply_to
        
        raw = base64.urlsafe_b64encode(message.as_string().encode("utf-8")).decode()
        body = {
            "raw": raw,
            "threadId": thread_id
        }
        
        try:
            self.service.users().messages().send(userId="me", body=body).execute()
        except Exception as e:
            print(f"[Gmail] Error sending reply: {str(e)}")
            raise

    # ------------------------------------------------------
    # SEND NEW EMAIL
    # ------------------------------------------------------
    def send_email(self, to_email, subject, body_text, attachments=None):
        """Send a new email (non-thread). Attachments optional (ignored if none)."""
        message = MIMEText(body_text)
        message["to"] = to_email
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw}
        self.service.users().messages().send(userId="me", body=body).execute()