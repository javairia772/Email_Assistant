# outlook_connector.py
import os
import requests
from Outlook.outlook_auth import OutlookAuth


class OutlookConnector:
    def __init__(self):
        self.auth = OutlookAuth()
        self.token = None

    def ensure_authenticated(self):
        if not self.token:
            self.token = self.auth.get_access_token()

    def _headers(self):
        if not self.token:
            raise Exception("User not authenticated.")
        return {"Authorization": f"Bearer {self.token}"}

    def list_messages(self, top=5):
        """Fetch the latest N emails"""
        self.ensure_authenticated()

        url = f"https://graph.microsoft.com/v1.0/me/messages?$top={top}"
        response = requests.get(url, headers=self._headers())

        # If token expired (401), re-authenticate and retry silently
        if response.status_code == 401:
            self.token = self.auth.get_access_token(force_refresh=True)
            response = requests.get(url, headers=self._headers())

        print("\n--- GRAPH DEBUG INFO ---")
        print("Status:", response.status_code)
        print("Response text:", response.text[:400])
        print("--- END DEBUG ---\n")

        if response.status_code == 200:
            data = response.json()
            emails = data.get("value", [])
            return [
                {
                    "id": e["id"],
                    "from": e["from"]["emailAddress"]["address"],
                    "subject": e["subject"],
                    "receivedDateTime": e["receivedDateTime"],
                }
                for e in emails
            ]
        else:
            raise Exception(f"Error fetching emails: {response.text}")

    def get_message(self, message_id):
        """Retrieve full email details by ID"""
        self.ensure_authenticated()

        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        response = requests.get(url, headers=self._headers())

        if response.status_code == 401:
            self.token = self.auth.get_access_token(force_refresh=True)
            response = requests.get(url, headers=self._headers())

        if response.status_code == 200:
            data = response.json()
            return {
                "id": data["id"],
                "subject": data["subject"],
                "from": data["from"]["emailAddress"]["address"],
                "body_preview": data.get("bodyPreview"),
                "body_content": data.get("body", {}).get("content"),
                "receivedDateTime": data["receivedDateTime"],
            }
        else:
            raise Exception(f"Error fetching message: {response.text}")
