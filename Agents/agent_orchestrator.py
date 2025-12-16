"""
Agent Orchestrator - Runs the Email Agent autonomously
Continuously processes emails and takes actions
"""
import time
import json
from datetime import datetime, timezone
from typing import List, Dict
from Agents.email_agent import EmailAgent
from Agents.agent_tools import AgentTools
from Gmail.gmail_connector import GmailConnector
from Outlook.outlook_connector import OutlookConnector
from providers.mcp_summaries_provider import McpSummariesProvider


class AgentOrchestrator:
    """
    Orchestrates the autonomous email agent
    - Fetches new emails
    - Processes them through the agent
    - Takes actions based on agent decisions
    - Logs all activities
    """
    
    def __init__(self, check_interval: int = 30):
        self.agent = EmailAgent()
        self.tools = AgentTools()
        self.gmail = GmailConnector()
        self.outlook = OutlookConnector()
        self.provider = McpSummariesProvider()
        self.check_interval = check_interval  # seconds
        self.running = False
        
        # Inject tools into agent
        tool_functions = self.tools.get_all_tools()
        for tool_name in self.agent.tools:
            if tool_name in tool_functions:
                self.agent.tools[tool_name]["function"] = tool_functions[tool_name]
    
    def process_single_email(self, email_data: Dict, source: str = "gmail") -> Dict:
        """Process a single email through the agent"""
        # Enrich email data
        enriched_email = {
            "id": email_data.get("id") or email_data.get("threadId"),
            "sender": email_data.get("sender", ""),
            "subject": email_data.get("subject", ""),
            "body": email_data.get("body") or email_data.get("snippet", ""),
            "source": source,
            "importance": email_data.get("importance", "Unknown"),
            "role": email_data.get("role", "Unknown")
        }
        
        # Get agent's decision
        result = self.agent.process_email(
            enriched_email,
            available_tools=self.tools.get_all_tools()
        )
        
        return result
    
    def fetch_and_process_emails(self, limit: int = 10) -> List[Dict]:
        """Fetch new emails and process them through the agent"""
        all_results = []
        
        # Fetch from Gmail
        try:
            print(f"[Agent] Fetching {limit} emails from Gmail...")
            gmail_threads = self.gmail.list_threads(max_results=limit)
            
            for thread in gmail_threads:
                result = self.process_single_email(thread, source="gmail")
                all_results.append(result)
                print(f"[Agent] Processed Gmail email: {thread.get('subject', 'No subject')}")
        except Exception as e:
            print(f"[Agent] Error processing Gmail: {e}")
        
        # Fetch from Outlook
        try:
            print(f"[Agent] Fetching {limit} emails from Outlook...")
            outlook_messages = self.outlook.list_messages(top=limit)
            
            for msg in outlook_messages:
                result = self.process_single_email(msg, source="outlook")
                all_results.append(result)
                print(f"[Agent] Processed Outlook email: {msg.get('subject', 'No subject')}")
        except Exception as e:
            print(f"[Agent] Error processing Outlook: {e}")
        
        return all_results
    
    def run_autonomous_loop(self):
        """Run the agent continuously in autonomous mode"""
        self.running = True
        print("\n" + "="*50)
        print("🤖 Email Agent - Autonomous Mode Started")
        print("="*50)
        
        while self.running:
            try:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Agent cycle starting...")
                
                # Fetch and process emails
                results = self.fetch_and_process_emails(limit=5)
                
                # Log results
                actions_taken = sum(len(r.get("actions_taken", [])) for r in results)
                print(f"[Agent] Processed {len(results)} emails, took {actions_taken} actions")
                
                # Print summary of actions
                for result in results:
                    if result.get("actions_taken"):
                        print(f"  📧 {result.get('email_id')}: {len(result['actions_taken'])} action(s)")
                        for action in result["actions_taken"]:
                            print(f"    - {action.get('action')}: {action.get('result', {}).get('message', '')}")
                
                # Save agent state
                self.agent._save_memory()
                
                print(f"[Agent] Sleeping for {self.check_interval} seconds...\n")
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                print("\n[Agent] Stopping agent...")
                self.running = False
                break
            except Exception as e:
                print(f"[Agent] Error in loop: {e}")
                time.sleep(self.check_interval)
    
    def process_high_priority_emails(self) -> List[Dict]:
        """Process only high-priority emails"""
        results = []
        
        # Get summaries to identify high-priority emails
        try:
            summaries = self.provider.get_summaries(limit=20)
            
            for summary in summaries:
                # Check if email is high priority
                threads = summary.get("threads", [])
                for thread in threads:
                    if thread.get("importance", "").lower() == "high":
                        email_data = {
                            "id": thread.get("id"),
                            "sender": summary.get("email"),
                            "subject": thread.get("subject", ""),
                            "body": thread.get("preview", ""),
                            "importance": "High",
                            "role": summary.get("role", "Unknown")
                        }
                        
                        result = self.process_single_email(
                            email_data,
                            source=summary.get("source", "gmail")
                        )
                        results.append(result)
        except Exception as e:
            print(f"[Agent] Error processing high-priority emails: {e}")
        
        return results
    
    def get_agent_stats(self) -> Dict:
        """Get statistics about agent's activity"""
        memory = self.agent.memory
        return {
            "total_contacts": len(memory.get("conversations", {})),
            "total_actions": len(memory.get("actions_taken", [])),
            "recent_actions": memory.get("actions_taken", [])[-10:],
            "memory_size": len(json.dumps(memory))
        }


if __name__ == "__main__":
    # Example: Run autonomous agent
    orchestrator = AgentOrchestrator(check_interval=60)  # Check every 60 seconds
    
    # Run in autonomous mode
    orchestrator.run_autonomous_loop()

