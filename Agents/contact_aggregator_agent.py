from datetime import datetime

class ContactAggregatorAgent:
    def __init__(self):
        self.contacts = {}

    def add_contact(self, name, email, thread_id, date=None):
        if email not in self.contacts:
            self.contacts[email] = {
                "name": name,
                "emails": [thread_id],
                "last_contacted": date
            }
        else:
            if thread_id not in self.contacts[email]["emails"]:
                self.contacts[email]["emails"].append(thread_id)
            # Update last_contacted if the new date is later
            if date:
                existing_date = self.contacts[email].get("last_contacted")
                if not existing_date or date > existing_date:
                    self.contacts[email]["last_contacted"] = date

    def process_email(self, email_obj):
        """
        email_obj: a Gmail thread object returned by get_message()
        It contains 'messages', each having 'payload' with headers.
        """
        for message in email_obj.get("messages", []):
            headers = message.get("payload", {}).get("headers", [])
            header_dict = {h["name"]: h["value"] for h in headers}
            thread_id = email_obj.get("id")
            date = header_dict.get("Date")
            # Convert to datetime if exists
            if date:
                try:
                    date = datetime.strptime(date[:25], "%a, %d %b %Y %H:%M:%S")
                except:
                    date = None

            # From
            if "From" in header_dict:
                name, email = self.parse_address(header_dict["From"])
                self.add_contact(name, email, thread_id, date)

            # To
            if "To" in header_dict:
                for n, e in self.parse_multiple_addresses(header_dict["To"]):
                    self.add_contact(n, e, thread_id, date)

            # CC
            if "Cc" in header_dict:
                for n, e in self.parse_multiple_addresses(header_dict["Cc"]):
                    self.add_contact(n, e, thread_id, date)

    def parse_address(self, addr_str):
        # Extract "Name <email@example.com>" or "email@example.com"
        import re
        match = re.match(r'(.*)<(.+@.+)>', addr_str)
        if match:
            name = match.group(1).strip('" ').strip()
            email = match.group(2).strip()
            return name, email
        else:
            return addr_str.strip(), addr_str.strip()

    def parse_multiple_addresses(self, addr_str):
        # Split multiple addresses separated by commas
        addresses = [a.strip() for a in addr_str.split(",")]
        return [self.parse_address(a) for a in addresses]

    def get_contacts(self):
        return self.contacts
