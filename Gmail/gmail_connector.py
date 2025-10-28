# Gmail/gmail_connector.py
from Gmail.gmail_auth import GmailAuth

class GmailConnector:
    def __init__(self):
        self.auth = GmailAuth()
        self.service = self.auth.authenticate()

    def list_threads(self, max_results=5):
        """List recent email threads."""
        results = self.service.users().threads().list(userId="me", maxResults=max_results).execute()
        return results.get("threads", [])

    def get_message(self, thread_id):
        """Get details for a specific thread."""
        thread = self.service.users().threads().get(userId="me", id=thread_id).execute()
        return thread
