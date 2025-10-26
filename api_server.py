from fastapi import FastAPI
from connectors.gmail_connector import list_threads, get_message
from Agents.contact_aggregator_agent import ContactAggregatorAgent  # <-- adjust filename if needed

app = FastAPI(title="Email Assistant API")

@app.get("/getContacts")
def get_contacts(limit: int = 10):
    """
    Fetch recent emails, process contacts, and return an aggregated contact list.
    """
    # Step 1: Initialize contact agent
    contact_agent = ContactAggregatorAgent()

    # Step 2: Get latest threads
    threads = list_threads(max_results=limit)

    # Step 3: For each thread, fetch full messages and process
    for t in threads:
        thread_data = get_message(t["id"])
        contact_agent.process_email(thread_data)

    # Step 4: Return aggregated contacts
    return contact_agent.get_contacts()
