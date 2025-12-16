"""
Agentic Email Assistant - Autonomous AI Agent
Uses ReAct pattern (Reasoning + Acting) for autonomous email management
"""
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


class EmailAgent:
    """
    Autonomous AI agent that can:
    - Analyze emails and make decisions
    - Plan multi-step workflows
    - Take actions (reply, prioritize, schedule)
    - Remember context and learn from patterns
    """
    
    def __init__(self, memory_path: str = "Agents/agent_memory.json"):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.memory_path = memory_path
        self.memory = self._load_memory()
        self.tools = self._register_tools()
        self.max_iterations = 10  # Prevent infinite loops
        
    def _load_memory(self) -> Dict:
        """Load agent's memory/state"""
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {
            "conversations": {},
            "preferences": {},
            "patterns": {},
            "actions_taken": []
        }
    
    def _save_memory(self):
        """Save agent's memory/state"""
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)
    
    def _register_tools(self) -> Dict:
        """Register available tools the agent can use"""
        return {
            "summarize_email": {
                "description": "Summarize an email thread to understand its content",
                "function": None  # Will be injected
            },
            "classify_email": {
                "description": "Classify email by role and importance",
                "function": None
            },
            "check_contact_history": {
                "description": "Check previous interactions with a contact",
                "function": None
            },
            "generate_reply": {
                "description": "Generate a reply to an email",
                "function": None
            },
            "prioritize_email": {
                "description": "Mark email as high/medium/low priority",
                "function": None
            },
            "schedule_followup": {
                "description": "Schedule a follow-up reminder for an email",
                "function": None
            },
            "extract_action_items": {
                "description": "Extract action items, deadlines, and next steps from email",
                "function": None
            }
        }
    
    def _call_llm(self, prompt: str, system_prompt: str = None) -> str:
        """Call Groq LLM with prompt"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _parse_agent_response(self, response: str) -> Dict:
        """Parse agent's response to extract thought, action, and parameters"""
        # Look for structured format: THOUGHT: ... ACTION: ... PARAMS: ...
        thought = ""
        action = None
        params = {}
        final_answer = ""
        
        lines = response.split("\n")
        current_section = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("THOUGHT:"):
                current_section = "thought"
                thought = line.replace("THOUGHT:", "").strip()
            elif line.startswith("ACTION:"):
                current_section = "action"
                action = line.replace("ACTION:", "").strip()
            elif line.startswith("PARAMS:"):
                current_section = "params"
                param_str = line.replace("PARAMS:", "").strip()
                try:
                    params = json.loads(param_str) if param_str else {}
                except:
                    pass
            elif line.startswith("ANSWER:"):
                current_section = "answer"
                final_answer = line.replace("ANSWER:", "").strip()
            else:
                if current_section == "thought":
                    thought += " " + line
                elif current_section == "answer":
                    final_answer += " " + line
        
        return {
            "thought": thought,
            "action": action,
            "params": params,
            "answer": final_answer or response
        }
    
    def _execute_action(self, action: str, params: Dict, context: Dict) -> Dict:
        """Execute an action using registered tools"""
        if action == "none" or not action:
            return {"status": "no_action", "result": "No action needed"}
        
        tool = self.tools.get(action)
        if not tool or not tool.get("function"):
            return {"status": "error", "result": f"Unknown action: {action}"}
        
        try:
            # Inject context into params
            params_with_context = {**params, "context": context}
            result = tool["function"](**params_with_context)
            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "result": str(e)}
    
    def process_email(self, email_data: Dict, available_tools: Dict = None) -> Dict:
        """
        Main agent loop: Analyze email and decide on actions
        
        Args:
            email_data: Email information (sender, subject, body, etc.)
            available_tools: Dictionary of tool functions to inject
        """
        # Inject tool functions
        if available_tools:
            for tool_name, tool_func in available_tools.items():
                if tool_name in self.tools:
                    self.tools[tool_name]["function"] = tool_func
        
        # Build context
        context = {
            "email": email_data,
            "memory": self.memory,
            "available_tools": list(self.tools.keys())
        }
        
        # Agent reasoning loop (ReAct pattern)
        iterations = 0
        action_history = []
        
        while iterations < self.max_iterations:
            iterations += 1
            
            # Build prompt for agent
            system_prompt = """You are an autonomous email assistant agent. Your job is to:
1. Understand the email content and context
2. Decide what actions to take (if any)
3. Use available tools to accomplish goals

Available tools:
""" + "\n".join([f"- {name}: {info['description']}" for name, info in self.tools.items()])

            user_prompt = f"""Analyze this email and decide what to do:

Email Data:
- From: {email_data.get('sender', 'Unknown')}
- Subject: {email_data.get('subject', 'No subject')}
- Body: {email_data.get('body', email_data.get('snippet', ''))[:500]}
- Importance: {email_data.get('importance', 'Unknown')}
- Role: {email_data.get('role', 'Unknown')}

Previous Actions: {json.dumps(action_history[-3:], indent=2) if action_history else "None"}

Respond in this format:
THOUGHT: [Your reasoning about what to do]
ACTION: [tool_name or "none" if no action needed]
PARAMS: [JSON object with parameters for the action, or {{}}]
ANSWER: [Final summary of what you decided and why]

If you need more information, use a tool. If you're done, set ACTION to "none"."""
            
            # Get agent's response
            response = self._call_llm(user_prompt, system_prompt)
            parsed = self._parse_agent_response(response)
            
            action_history.append({
                "iteration": iterations,
                "thought": parsed["thought"],
                "action": parsed["action"],
                "params": parsed["params"]
            })
            
            # Execute action if needed
            if parsed["action"] and parsed["action"] != "none":
                action_result = self._execute_action(parsed["action"], parsed["params"], context)
                action_history[-1]["result"] = action_result
                
                # If action was successful and agent says it's done, break
                if action_result.get("status") == "success" and "done" in parsed["answer"].lower():
                    break
            else:
                # No action needed, agent is done
                break
        
        # Update memory
        self._update_memory(email_data, action_history)
        
        return {
            "email_id": email_data.get("id"),
            "decisions": action_history,
            "final_answer": parsed.get("answer", ""),
            "actions_taken": [a for a in action_history if a.get("action") != "none"]
        }
    
    def _update_memory(self, email_data: Dict, action_history: List):
        """Update agent's memory with new information"""
        sender = email_data.get("sender", "unknown")
        
        # Track conversation patterns
        if sender not in self.memory["conversations"]:
            self.memory["conversations"][sender] = []
        
        self.memory["conversations"][sender].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subject": email_data.get("subject"),
            "actions": action_history
        })
        
        # Track actions taken
        for action in action_history:
            if action.get("action") != "none":
                self.memory["actions_taken"].append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": action.get("action"),
                    "email": email_data.get("id")
                })
        
        # Keep only last 100 actions
        if len(self.memory["actions_taken"]) > 100:
            self.memory["actions_taken"] = self.memory["actions_taken"][-100:]
        
        self._save_memory()
    
    def batch_process_emails(self, emails: List[Dict], available_tools: Dict = None) -> List[Dict]:
        """Process multiple emails autonomously"""
        results = []
        for email in emails:
            result = self.process_email(email, available_tools)
            results.append(result)
        return results

