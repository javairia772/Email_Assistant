# Outlook/outlook_connector.py
import requests
from Outlook.outlook_auth import OutlookAuth


class OutlookConnector:
    """
    Provides methods to fetch, normalize, and summarize Outlook email data
    via Microsoft Graph API.
    Automatically detects logged-in mailbox (so no need to pass your own address).
    """

    def __init__(self):
        self.auth = OutlookAuth()
        self.token = None
        self.user_email = None  # Detected mailbox address

    # ------------------------------------------------------
    # AUTH & HELPERS
    # ------------------------------------------------------
    def ensure_authenticated(self):
        """Ensure valid access token and detect logged-in Outlook account."""
        if not self.token:
            self.token = self.auth.get_access_token()

        if not self.user_email:
            # Detect mailbox identity
            url = "https://graph.microsoft.com/v1.0/me"
            resp = requests.get(url, headers=self._headers())
            if resp.status_code == 200:
                self.user_email = resp.json().get("userPrincipalName") or resp.json().get("mail")
                print(f"✅ Detected Outlook mailbox: {self.user_email}")
            else:
                raise Exception(f"Failed to detect user mailbox: {resp.text}")

    def _headers(self):
        if not self.token:
            raise Exception("User not authenticated.")
        return {"Authorization": f"Bearer {self.token}"}

    # ------------------------------------------------------
    # SEND NEW EMAIL
    # ------------------------------------------------------
    def send_email(self, to_email, subject, body_text, attachments=None):
        """Send a new Outlook email via Graph API."""
        self.ensure_authenticated()
        url = "https://graph.microsoft.com/v1.0/me/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": True,
        }
        resp = requests.post(url, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
        if resp.status_code not in (200, 202):
            raise Exception(f"Outlook send failed: {resp.text}")

    # ------------------------------------------------------
    # LIST MESSAGES
    # ------------------------------------------------------
    def list_messages(self, top=5):
        """Fetch the latest N emails."""
        self.ensure_authenticated()
        url = (
            f"https://graph.microsoft.com/v1.0/me/messages"
            f"?$top={top}&$select=id,subject,from,toRecipients,body,bodyPreview,receivedDateTime"
        )

        response = requests.get(url, headers=self._headers())

        if response.status_code == 401:
            self.token = self.auth.get_access_token(force_refresh=True)
            response = requests.get(url, headers=self._headers())

        if response.status_code == 200:
            data = response.json()
            emails = data.get("value", [])
            return [self._normalize_message(e) for e in emails]
        else:
            raise Exception(f"Error fetching emails: {response.text}")

    # ------------------------------------------------------
    # FETCH THREADS (AUTO CONTACT DETECTION)
    # ------------------------------------------------------
    def fetch_threads(self, contact_email=None, top=50, auto=True):
        """
        Fetch messages grouped by conversationId.
        If contact_email is None, automatically uses logged-in mailbox for filtering.
        """
        self.ensure_authenticated()
        contact_email = contact_email or self.user_email

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

            if (
                contact_email.lower() == sender.lower()
                or contact_email.lower() in [r.lower() for r in recipients]
            ):
                thread_id = msg.get("conversationId", "unknown")
                threads.setdefault(thread_id, []).append({
                    "id": msg.get("id"),
                    "sender": sender,
                    "subject": msg.get("subject", ""),
                    "body": msg.get("body", {}).get("content", msg.get("bodyPreview", "")),
                    "date": msg.get("receivedDateTime", "")
                })

        # ✅ Summarization integration
        from Summarizer.summarize_helper import summarize_thread_logic, summarize_contact_logic

        for thread_id, msgs in threads.items():
            summarize_thread_logic("outlook", contact_email, thread_id, thread_obj=msgs, force=False)

        summarize_contact_logic(
            "outlook", contact_email, lambda e: self.fetch_threads(e, auto=False),
            top=50, force_refresh=False
        )

        print(f"📨 Fetched {len(threads)} Outlook threads for {contact_email}")
        return list(threads.values())

    def fetch_thread_by_id(self, contact_email: str, conversation_id: str, top: int = 50):
        """
        Fetch a specific conversation (thread) by conversationId for a contact.
        Does not trigger summarization to keep this lightweight for the UI.
        """
        self.ensure_authenticated()
        contact_email = contact_email or self.user_email
        url = (
            "https://graph.microsoft.com/v1.0/me/messages"
            f"?$filter=conversationId eq '{conversation_id}'"
            f"&$orderby=receivedDateTime asc"
            f"&$top={top}"
            f"&$select=id,conversationId,subject,from,toRecipients,body,bodyPreview,receivedDateTime"
        )
        response = requests.get(url, headers=self._headers())
        if response.status_code == 401:
            self.token = self.auth.get_access_token(force_refresh=True)
            response = requests.get(url, headers=self._headers())

        if response.status_code != 200:
            raise Exception(f"Error fetching conversation: {response.text}")

        data = response.json()
        messages = data.get("value", [])
        parsed = []
        for msg in messages:
            parsed.append({
                "id": msg.get("id"),
                "sender": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                "subject": msg.get("subject", ""),
                "body": msg.get("body", {}).get("content", msg.get("bodyPreview", "")),
                "date": msg.get("receivedDateTime", ""),
            })
        return parsed

    # ------------------------------------------------------
    # NORMALIZE MESSAGE
    # ------------------------------------------------------
    def _normalize_message(self, msg, full=False):
        from_field = msg.get("from") or {}
        email_addr = from_field.get("emailAddress") or {}
        sender = email_addr.get("address") or from_field.get("name") or "Unknown Sender"

        body_content = msg.get("body", {}).get("content", "")
        if not body_content:
            body_content = msg.get("bodyPreview", "")

        return {
            "id": msg.get("id", ""),
            "sender": sender,
            "subject": msg.get("subject", ""),
            "body": body_content,
            "date": msg.get("receivedDateTime", ""),
        }



    # ------------------------------------------------------
    # GET MESSAGE AS TEXT
    # ------------------------------------------------------
    def get_thread_text(self, message_id):
        msg = self.get_message(message_id)
        if not msg:
            return "No message content."
        return f"From: {msg['sender']}\nSubject: {msg['subject']}\n\n{msg['body']}\n"

    def get_message(self, message_id):
        """Retrieve full email details by ID."""
        self.ensure_authenticated()
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        response = requests.get(url, headers=self._headers())

        if response.status_code == 401:
            self.token = self.auth.get_access_token(force_refresh=True)
            response = requests.get(url, headers=self._headers())

        if response.status_code == 200:
            return self._normalize_message(response.json(), full=True)
        else:
            raise Exception(f"Error fetching message: {response.text}")

    # ------------------------------------------------------
    # SEND REPLY
    # ------------------------------------------------------
    def send_reply(self, message_id, to_email, subject, reply_body, thread_id=None):
        """
        Send an Outlook reply within the same thread.
        
        Args:
            message_id: The ID of the message being replied to
            to_email: The email address to send the reply to
            subject: The email subject
            reply_body: The body of the reply
            thread_id: The conversation ID (optional, used for logging)
        """
        self.ensure_authenticated()
        headers = {**self._headers(), "Content-Type": "application/json"}
        
        if not message_id:
            # Fallback to creating a new message if no message_id is provided
            return self.send_email(to_email, subject, reply_body)
            
        try:
            # First, get the original message to include in the reply
            msg_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}?$select=conversationId,internetMessageId,sender"
            msg_resp = requests.get(msg_url, headers=headers)
            
            if msg_resp.status_code != 200:
                print(f"[Outlook] Failed to get message details: {msg_resp.text}")
                # Fallback to basic reply if we can't get message details
                return self.send_email(to_email, subject, reply_body)
                
            msg_data = msg_resp.json()
            conversation_id = msg_data.get('conversationId')
            
            # Format the reply to include the original message
            formatted_body = f"{reply_body}\n\n---\nOriginal message:\n{'-'*20}\n"
            
            # Get the sender's email address from the profile
            me = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers).json()
            sender_email = me.get('mail') or me.get('userPrincipalName')
            
            # Send the reply using the reply endpoint to maintain thread
            url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply"
            payload = {
                "message": {
                    "from": {
                        "emailAddress": {
                            "address": sender_email
                        }
                    },
                    "body": {
                        "contentType": "Text",
                        "content": formatted_body
                    }
                },
                "comment": ""
            }
            
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code not in (200, 202):
                print(f"[Outlook] Failed to send reply: {response.text}")
                # Fallback to basic send if reply fails
                return self.send_email(to_email, subject, reply_body)
                
            print(f"[Outlook] Reply sent successfully (Conversation: {conversation_id})")
            return True
            
        except Exception as e:
            print(f"[Outlook] Error sending reply: {str(e)}")
            # Fallback to basic send if anything goes wrong
            return self.send_email(to_email, subject, reply_body)