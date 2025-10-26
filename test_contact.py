from connectors.gmail_connector import list_threads, get_message
from Agents.contact_aggregator_agent import ContactAggregatorAgent

# Initialize the agent
contact_agent = ContactAggregatorAgent()

# Fetch threads directly
threads = list_threads(max_results=5)

for t in threads:
    thread_id = t.get("id")
    if thread_id:
        thread_obj = get_message(thread_id)
        contact_agent.process_email(thread_obj)

# Get contacts
contacts = contact_agent.get_contacts()

# Print results
for email, info in contacts.items():
    print(email, info)
# After printing contacts
import json

with open("contacts.json", "w") as f:
    json.dump(
        {
            k: {
                "name": v["name"],
                "emails": v["emails"],
                "last_contacted": str(v["last_contacted"])
            } 
            for k, v in contacts.items()
        },
        f,
        indent=4
    )

print("Contacts saved to contacts.json")
