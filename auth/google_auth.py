from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle, os

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def gmail_login():
    creds = None
    if os.path.exists("token_gmail.pkl"):
        creds = pickle.load(open("token_gmail.pkl", "rb"))
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=8080)
        with open("token_gmail.pkl", "wb") as f:
            pickle.dump(creds, f)
    service = build("gmail", "v1", credentials=creds)
    return service
