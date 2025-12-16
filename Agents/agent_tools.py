"""
Tool implementations for the Email Agent
These tools can be used by the agent to take actions
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import json
from Summarizer.groq_summarizer import GroqSummarizer
from classifier.email_classifier import classify_email


class AgentTools:
    """Collection of tools the agent can use"""
    
    def __init__(self):
        self.summarizer = GroqSummarizer()
        self.action_log = []
    
    def summarize_email(self, email_id: str, source: str, contact_email: str, 
                       thread_obj: Any = None, context: Dict = None) -> Dict:
        """Tool: Summarize an email thread"""
        try:
            from Summarizer.summarize_helper import summarize_thread_logic
            
            result = summarize_thread_logic(
                source=source,
                contact_email=contact_email,
                thread_id=email_id,
                thread_obj=thread_obj
            )
            
            return {
                "tool": "summarize_email",
                "success": "summary" in result,
                "summary": result.get("summary", ""),
                "cached": result.get("used_cache", False)
            }
        except Exception as e:
            return {"tool": "summarize_email", "success": False, "error": str(e)}
    
    def classify_email(self, sender: str, subject: str, body: str, 
                      context: Dict = None) -> Dict:
        """Tool: Classify email by role and importance"""
        try:
            classification = classify_email(sender, subject, body)
            return {
                "tool": "classify_email",
                "success": True,
                "role": classification.get("role"),
                "importance": classification.get("importance"),
                "role_confidence": classification.get("role_confidence"),
                "importance_confidence": classification.get("importance_confidence")
            }
        except Exception as e:
            return {"tool": "classify_email", "success": False, "error": str(e)}
    
    def check_contact_history(self, contact_email: str, context: Dict = None) -> Dict:
        """Tool: Check previous interactions with a contact"""
        try:
            memory = context.get("memory", {}) if context else {}
            conversations = memory.get("conversations", {}).get(contact_email, [])
            
            # Get recent interactions
            recent = conversations[-5:] if len(conversations) > 5 else conversations
            
            return {
                "tool": "check_contact_history",
                "success": True,
                "contact": contact_email,
                "total_interactions": len(conversations),
                "recent_interactions": recent
            }
        except Exception as e:
            return {"tool": "check_contact_history", "success": False, "error": str(e)}
    
    def generate_reply(self, email_id: str, sender: str, subject: str, body: str,
                      summary: str = "", context: Dict = None) -> Dict:
        """Tool: Generate a reply to an email using LLM"""
        try:
            prompt = f"""You are an email assistant helping a busy professional write a reply.

Original Email:
From: {sender}
Subject: {subject}
Body: {body}

Summary: {summary}

Generate a professional, concise reply. Consider:
- The tone and context of the original email
- Whether a reply is needed (some emails don't need responses)
- Keep it brief and actionable
- Match the formality level of the original

If no reply is needed, say "No reply needed" and explain why.
Otherwise, write the reply directly (no greetings like "Here's a reply:")."""

            response = self.summarizer._run_groq_model(prompt)
            
            return {
                "tool": "generate_reply",
                "success": True,
                "reply": response,
                "email_id": email_id
            }
        except Exception as e:
            return {"tool": "generate_reply", "success": False, "error": str(e)}
    
    def prioritize_email(self, email_id: str, priority: str, reason: str = "",
                        context: Dict = None) -> Dict:
        """Tool: Mark email as high/medium/low priority"""
        try:
            # Validate priority
            if priority.lower() not in ["high", "medium", "low"]:
                return {
                    "tool": "prioritize_email",
                    "success": False,
                    "error": "Priority must be high, medium, or low"
                }
            
            # Store priority (in real implementation, this would update email labels)
            priority_data = {
                "email_id": email_id,
                "priority": priority.lower(),
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self.action_log.append(priority_data)
            
            return {
                "tool": "prioritize_email",
                "success": True,
                "email_id": email_id,
                "priority": priority.lower(),
                "message": f"Email marked as {priority.lower()} priority"
            }
        except Exception as e:
            return {"tool": "prioritize_email", "success": False, "error": str(e)}
    
    def schedule_followup(self, email_id: str, days: int = 3, note: str = "",
                         context: Dict = None) -> Dict:
        """Tool: Schedule a follow-up reminder for an email"""
        try:
            followup_date = datetime.now(timezone.utc) + timedelta(days=days)
            
            followup_data = {
                "email_id": email_id,
                "followup_date": followup_date.isoformat(),
                "note": note,
                "created": datetime.now(timezone.utc).isoformat()
            }
            
            self.action_log.append(followup_data)
            
            return {
                "tool": "schedule_followup",
                "success": True,
                "email_id": email_id,
                "followup_date": followup_date.isoformat(),
                "message": f"Follow-up scheduled for {followup_date.strftime('%Y-%m-%d')}"
            }
        except Exception as e:
            return {"tool": "schedule_followup", "success": False, "error": str(e)}
    
    def extract_action_items(self, email_id: str, subject: str, body: str,
                            summary: str = "", context: Dict = None) -> Dict:
        """Tool: Extract action items, deadlines, and next steps from email"""
        try:
            prompt = f"""Extract action items, deadlines, and next steps from this email:

Subject: {subject}
Body: {body}
Summary: {summary}

Return a JSON object with:
- action_items: list of specific tasks mentioned
- deadlines: list of dates/deadlines mentioned
- next_steps: list of suggested next steps
- requires_response: boolean (does this email need a reply?)

Format as JSON only, no other text."""

            response = self.summarizer._run_groq_model(prompt)
            
            # Try to parse JSON from response
            try:
                # Extract JSON if wrapped in markdown
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()
                
                action_data = json.loads(response)
            except:
                # Fallback: create structured response
                action_data = {
                    "action_items": [],
                    "deadlines": [],
                    "next_steps": [],
                    "requires_response": "reply" in response.lower() or "respond" in response.lower()
                }
            
            return {
                "tool": "extract_action_items",
                "success": True,
                "email_id": email_id,
                "data": action_data
            }
        except Exception as e:
            return {"tool": "extract_action_items", "success": False, "error": str(e)}
    
    def get_all_tools(self) -> Dict:
        """Get all tool functions as a dictionary for the agent"""
        return {
            "summarize_email": self.summarize_email,
            "classify_email": self.classify_email,
            "check_contact_history": self.check_contact_history,
            "generate_reply": self.generate_reply,
            "prioritize_email": self.prioritize_email,
            "schedule_followup": self.schedule_followup,
            "extract_action_items": self.extract_action_items
        }

