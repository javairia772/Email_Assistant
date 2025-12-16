"""
Example usage of the Agentic Email Assistant
Shows different ways to use the agent
"""
from Agents.email_agent import EmailAgent
from Agents.agent_tools import AgentTools
from Agents.agent_orchestrator import AgentOrchestrator


def example_single_email():
    """Example: Process a single email through the agent"""
    print("=" * 50)
    print("Example 1: Processing a Single Email")
    print("=" * 50)
    
    # Initialize agent and tools
    agent = EmailAgent()
    tools = AgentTools()
    
    # Sample email
    email_data = {
        "id": "email_123",
        "sender": "student@university.edu",
        "subject": "Urgent: Assignment Extension Request",
        "body": "Dear Professor, I need an extension on the assignment due tomorrow. I had a family emergency.",
        "importance": "High",
        "role": "Student"
    }
    
    # Process through agent
    result = agent.process_email(
        email_data,
        available_tools=tools.get_all_tools()
    )
    
    print(f"\nEmail: {email_data['subject']}")
    print(f"Decisions made: {len(result['decisions'])}")
    print(f"Actions taken: {len(result['actions_taken'])}")
    
    for action in result['actions_taken']:
        print(f"\n  Action: {action['action']}")
        print(f"  Result: {action.get('result', {}).get('message', 'N/A')}")
    
    print(f"\nFinal Answer: {result['final_answer']}")


def example_batch_processing():
    """Example: Process multiple emails"""
    print("\n" + "=" * 50)
    print("Example 2: Batch Processing Emails")
    print("=" * 50)
    
    agent = EmailAgent()
    tools = AgentTools()
    
    emails = [
        {
            "id": "email_1",
            "sender": "faculty@university.edu",
            "subject": "Meeting Request",
            "body": "Can we schedule a meeting next week?",
            "importance": "Medium",
            "role": "Faculty"
        },
        {
            "id": "email_2",
            "sender": "vendor@company.com",
            "subject": "Product Promotion",
            "body": "Check out our new product!",
            "importance": "Low",
            "role": "Vendor"
        }
    ]
    
    results = agent.batch_process_emails(emails, tools.get_all_tools())
    
    for i, result in enumerate(results):
        print(f"\nEmail {i+1}: {emails[i]['subject']}")
        print(f"  Actions: {len(result['actions_taken'])}")


def example_autonomous_mode():
    """Example: Run agent in autonomous mode"""
    print("\n" + "=" * 50)
    print("Example 3: Autonomous Agent Mode")
    print("=" * 50)
    print("This will run continuously and process emails automatically")
    print("Press Ctrl+C to stop")
    
    orchestrator = AgentOrchestrator(check_interval=30)
    
    # Run for a limited time (or use run_autonomous_loop() for continuous)
    print("\nRunning agent for 1 cycle...")
    results = orchestrator.fetch_and_process_emails(limit=3)
    
    print(f"\nProcessed {len(results)} emails")
    for result in results:
        if result.get('actions_taken'):
            print(f"  Email {result.get('email_id')}: {len(result['actions_taken'])} actions")


def example_high_priority_only():
    """Example: Process only high-priority emails"""
    print("\n" + "=" * 50)
    print("Example 4: High-Priority Email Processing")
    print("=" * 50)
    
    orchestrator = AgentOrchestrator()
    results = orchestrator.process_high_priority_emails()
    
    print(f"Found {len(results)} high-priority emails")
    for result in results:
        print(f"  Processed: {result.get('email_id')}")


def example_agent_stats():
    """Example: Get agent statistics"""
    print("\n" + "=" * 50)
    print("Example 5: Agent Statistics")
    print("=" * 50)
    
    orchestrator = AgentOrchestrator()
    stats = orchestrator.get_agent_stats()
    
    print(f"Total contacts: {stats['total_contacts']}")
    print(f"Total actions: {stats['total_actions']}")
    print(f"Recent actions: {len(stats['recent_actions'])}")
    
    if stats['recent_actions']:
        print("\nRecent actions:")
        for action in stats['recent_actions'][-5:]:
            print(f"  - {action.get('action')} at {action.get('timestamp')}")


if __name__ == "__main__":
    # Run examples
    try:
        example_single_email()
        example_batch_processing()
        example_high_priority_only()
        example_agent_stats()
        
        # Uncomment to run autonomous mode (runs continuously)
        # example_autonomous_mode()
        
    except KeyboardInterrupt:
        print("\n\nExamples stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

