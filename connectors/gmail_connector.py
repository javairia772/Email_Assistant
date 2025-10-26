from auth.google_auth import gmail_login

def list_threads(max_results=5):
    service = gmail_login()
    results = service.users().threads().list(userId="me", maxResults=max_results).execute()
    return results.get("threads", [])

def get_message(thread_id):
    service = gmail_login()
    thread = service.users().threads().get(userId="me", id=thread_id).execute()
    return thread
    
def get_gmail_service():
    """Return an authenticated Gmail API service."""
    return gmail_login()
