# -*- coding: utf-8 -*-
"""
run_contact_flow.py
Clean version (no emojis or Unicode symbols)
"""

from connectors.gmail_connector import list_threads, get_message
from Agents.contact_aggregator_agent import ContactAggregatorAgent
import json
import os

def fetch_threads_and_messages(max_threads=5):
    """Fetch email threads and messages from Gmail."""
    threads = list_threads(max_results=max_threads)
    results = []
    for t in threads:
        tid = t.get("id")
        if not tid:
            continue
        thread_obj = get_message(tid)
        results.append(thread_obj)
    return results


if __name__ == "__main__":
    print("Starting Gmail thread fetch process...")
    threads = fetch_threads_and_messages(max_threads=5)
    print(f"Fetched {len(threads)} thread objects.")

    # Run the ContactAggregatorAgent
    print("Running ContactAggregatorAgent for contact extraction...")
    agent = ContactAggregatorAgent()
    contacts = agent.run(threads)

    # Save contacts to JSON file in UTF-8 encoding
    contacts_data = {"contacts": contacts}
    with open("contacts.json", "w", encoding="utf-8") as f:
        json.dump(contacts_data, f, ensure_ascii=False, indent=2)

    print(f"Extracted {len(contacts)} unique contact(s). Saved to contacts.json.")

    # Optional: send data to backend (enable when backend is active)
    """
    import requests
    try:
        response = requests.post("http://localhost:5000/getContacts", json=contacts_data)
        if response.status_code == 200:
            print("Contacts successfully sent to backend dashboard.")
        else:
            print(f"Backend responded with status {response.status_code}")
    except Exception as e:
        print(f"Could not connect to backend: {e}")
    """
