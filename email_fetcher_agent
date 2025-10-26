
# email_fetcher_agent.py
import imaplib
import email
from email.header import decode_header


class EmailFetcherAgent:
    def __init__(self, imap_server, email_user, email_pass):
        self.imap_server = imap_server
        self.email_user = email_user
        self.email_pass = email_pass

    def fetch_latest_emails(self, n=5):
        """Fetch the latest n unread emails"""
        mail = imaplib.IMAP4_SSL(self.imap_server)
        mail.login(self.email_user, self.email_pass)
        mail.select("inbox")

        # Search unread messages
        status, messages = mail.search(None, '(UNSEEN)')
        email_ids = messages[0].split()

        latest_emails = []
        for eid in email_ids[-n:]:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8", errors="ignore")

            from_ = msg.get("From")
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            latest_emails.append({
                "from": from_,
                "subject": subject,
                "body": body[:300] + "..."  # preview
            })

        mail.logout()
        return latest_emails
