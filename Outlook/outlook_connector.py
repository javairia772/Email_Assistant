# Outlook/outlook_connector.py
import requests
from Outlook.outlook_auth import OutlookAuth


class OutlookConnector:
    def __init__(self):
        self.auth = OutlookAuth()
        self.token = None

    # ------------------------------------------------------
    # AUTH & HELPERS
    # ------------------------------------------------------
    def ensure_authenticated(self):
        if not self.token:
            self.token = self.auth.authenticate()

    def _headers(self):
        if not self.token:
            raise Exception("User not authenticated.")
        return {"Authorization": f"Bearer {self.token}"}

    # ------------------------------------------------------
    # LIST MESSAGES
    # ------------------------------------------------------
    def list_messages(self, top=5):
        """Fetch the latest N emails."""
        self.ensure_authenticated()

        url = f"https://graph.microsoft.com/v1.0/me/messages?$top={top}"
        response = requests.get(url, headers=self._headers())

        if response.status_code == 200:
            data = response.json()
            emails = data.get("value", [])
            return [self._normalize_message(e) for e in emails]
        else:
            raise Exception(f"Error fetching emails: {response.text}")

    # ------------------------------------------------------
    # GET FULL MESSAGE
    # ------------------------------------------------------
    def get_message(self, message_id):
        """Retrieve full email details by ID."""
        self.ensure_authenticated()

        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        response = requests.get(url, headers=self._headers())

        if response.status_code == 200:
            data = response.json()
            return self._normalize_message(data, full=True)
        else:
            raise Exception(f"Error fetching message: {response.text}")

    # ------------------------------------------------------
    # NEW: FETCH THREADS BY CONTACT
    # ------------------------------------------------------

    def fetch_threads(self, contact_email: str, top: int = 50):
        """
        Fetch all messages involving a specific contact, grouped by conversationId.
        Each thread is a list of dicts with sender, subject, body, etc.
        """
        self.ensure_authenticated()
        url = (
            "https://graph.microsoft.com/v1.0/me/messages"
            f"?$select=id,conversationId,subject,from,toRecipients,body,bodyPreview,receivedDateTime"
            f"&$top={top}"
        )
        response = requests.get(url, headers=self._headers())

        if response.status_code != 200:
            raise Exception(f"Error fetching messages: {response.text}")

        data = response.json()
        messages = data.get("value", [])

        threads = {}
        for msg in messages:
            sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
            recipients = [
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("toRecipients", [])
            ]
            # Check if the contact is involved in this message
            if contact_email.lower() == sender.lower() or contact_email.lower() in [r.lower() for r in recipients]:
                thread_id = msg.get("conversationId", "unknown")
                if thread_id not in threads:
                    threads[thread_id] = []
                threads[thread_id].append({
                    "id": msg.get("id"),
                    "sender": sender,
                    "subject": msg.get("subject", ""),
                    "body": msg.get("body", {}).get("content", msg.get("bodyPreview", "")),
                    "date": msg.get("receivedDateTime", "")
                })

        # Convert dict of threads → list of thread message lists
        return list(threads.values())



    # ------------------------------------------------------
    # INTERNAL: NORMALIZER
    # ------------------------------------------------------
    def _normalize_message(self, msg, full=False):
        """
        Normalize Outlook message data into a summarizer-friendly dict.
        """
        try:
            sender = (
                msg.get("from", {})
                .get("emailAddress", {})
                .get("address", "")
            )
        except Exception:
            sender = ""

        return {
            "id": msg.get("id", ""),
            "sender": sender,
            "subject": msg.get("subject", ""),
            "body": (
                msg.get("body", {}).get("content", "")
                if full
                else msg.get("bodyPreview", "")
            ),
            "date": msg.get("receivedDateTime", ""),
        }

    # ------------------------------------------------------
    # OPTIONAL: GET MESSAGE AS CLEAN TEXT
    # ------------------------------------------------------
    def get_thread_text(self, message_id):
        """
        Return a cleaned text representation of an email.
        """
        msg = self.get_message(message_id)
        if not msg:
            return "No message content."
        return f"From: {msg['sender']}\nSubject: {msg['subject']}\n\n{msg['body']}\n"

    from urllib.parse import quote

    def fetch_threads_by_conversation(self, conversation_id):
        """
        Fetch all messages in a given Outlook conversation by conversationId.
        Returns a list of normalized message dicts.
        """
        self.ensure_authenticated()

        # Fetch a batch of recent messages (instead of filtering via query)
        url = (
            "https://graph.microsoft.com/v1.0/me/messages"
            "?$select=id,conversationId,subject,from,body,bodyPreview,receivedDateTime"
            "&$top=200"
        )

        response = requests.get(url, headers=self._headers())

        if response.status_code != 200:
            raise Exception(f"Error fetching messages: {response.text}")

        data = response.json()
        messages = data.get("value", [])

        # ✅ Filter locally by conversation ID
        filtered_msgs = [
            msg for msg in messages
            if msg.get("conversationId") == conversation_id
        ]

        thread = []
        for msg in filtered_msgs:
            sender = (
                msg.get("from", {})
                .get("emailAddress", {})
                .get("address", "")
            )
            subject = msg.get("subject", "")
            body = msg.get("body", {}).get("content", msg.get("bodyPreview", ""))
            date = msg.get("receivedDateTime", "")

            thread.append({
                "id": msg.get("id"),
                "sender": sender,
                "subject": subject,
                "body": body,
                "date": date,
            })

        if not thread:
            raise Exception(f"No messages found for conversation {conversation_id}")

        return thread
