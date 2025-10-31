# Gmail/gmail_connector.py
from Gmail.gmail_auth import GmailAuth
import base64
from googleapiclient.errors import HttpError
# Import summarization logic (Groq + caching)
from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic


class GmailConnector:
    def __init__(self):
        self.auth = GmailAuth()
        self.service = self.auth.authenticate()

    # ------------------------------------------------------
    # List threads (already fine)
    # ------------------------------------------------------
    def list_threads(self, max_results=5):
        """List recent email threads."""
        try:
            results = self.service.users().threads().list(userId="me", maxResults=max_results).execute()
            return results.get("threads", [])
        except HttpError as e:
            return {"error": f"Gmail API error: {e}"}

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
    def fetch_threads(self, contact_email, max_results=10, auto=True):
        """
        Fetch all threads that include a given contact email.
        If auto=False, skip auto-summarization to avoid recursion.
        """
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
            summarize_thread_logic("gmail", contact_email, thread_id, thread_obj=thread_obj, force=False)
        except Exception as e:
            print(f"[AutoSummarize] Failed for {contact_email} thread {thread_id}: {e}")


    # ------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------
    def _parse_thread(self, thread):
        """
        Normalize Gmail thread into list[dict] of:
        {
            'sender': str,
            'subject': str,
            'body': str,
            'date': str
        }
        """
        messages = thread.get("messages", [])
        parsed = []
        for msg in messages:
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

            sender = headers.get("From", "")
            subject = headers.get("Subject", "")
            date = headers.get("Date", "")

            # Try to decode message body (plain text or HTML)
            body = ""
            if "parts" in msg["payload"]:
                for part in msg["payload"]["parts"]:
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body = self._decode_base64(part["body"]["data"])
                        break
            else:
                body = self._decode_base64(msg["payload"]["body"].get("data", ""))

            parsed.append({
                "sender": sender,
                "subject": subject,
                "body": body.strip(),
                "date": date
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


