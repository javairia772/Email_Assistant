# 🤖 Agentic Email Assistant

## Overview

This directory contains an **autonomous AI agent** that can intelligently process emails, make decisions, and take actions without human intervention.

## Key Features

### 🧠 Autonomous Decision Making
- **ReAct Pattern**: The agent uses Reasoning + Acting to analyze emails and decide on actions
- **Multi-step Planning**: Can break down complex tasks into steps
- **Context Awareness**: Remembers previous interactions and learns patterns

### 🛠️ Available Tools
The agent has access to these tools:

1. **summarize_email** - Summarize email threads
2. **classify_email** - Classify by role and importance
3. **check_contact_history** - Review past interactions
4. **generate_reply** - Generate email replies
5. **prioritize_email** - Mark emails as high/medium/low priority
6. **schedule_followup** - Schedule follow-up reminders
7. **extract_action_items** - Extract tasks, deadlines, and next steps

### 📝 Memory & Learning
- **Conversation History**: Tracks interactions with each contact
- **Action Log**: Records all actions taken
- **Pattern Recognition**: Learns from past decisions

## Architecture

```
EmailAgent (email_agent.py)
    ├── ReAct Loop (Reasoning + Acting)
    ├── Tool Execution
    └── Memory Management

AgentTools (agent_tools.py)
    ├── Email Operations
    ├── Classification
    └── Action Taking

AgentOrchestrator (agent_orchestrator.py)
    ├── Email Fetching
    ├── Batch Processing
    └── Autonomous Loop
```

## Usage

### 1. Process a Single Email

```python
from Agents.email_agent import EmailAgent
from Agents.agent_tools import AgentTools

agent = EmailAgent()
tools = AgentTools()

email_data = {
    "id": "email_123",
    "sender": "student@university.edu",
    "subject": "Assignment Help",
    "body": "I need help with the assignment...",
    "importance": "High",
    "role": "Student"
}

result = agent.process_email(email_data, tools.get_all_tools())
print(result['final_answer'])
```

### 2. Run Autonomous Mode

```python
from Agents.agent_orchestrator import AgentOrchestrator

orchestrator = AgentOrchestrator(check_interval=60)
orchestrator.run_autonomous_loop()  # Runs continuously
```

### 3. Process High-Priority Emails Only

```python
orchestrator = AgentOrchestrator()
results = orchestrator.process_high_priority_emails()
```

## How It Works

### ReAct Pattern

1. **Reasoning**: Agent analyzes the email and decides what to do
2. **Acting**: Agent uses tools to take actions
3. **Observing**: Agent sees results and adjusts
4. **Repeat**: Until goal is achieved or no more actions needed

### Example Flow

```
Email arrives → Agent analyzes
    ↓
Agent thinks: "This is urgent, needs reply"
    ↓
Agent uses: classify_email → prioritize_email → generate_reply
    ↓
Agent saves: Actions to memory
    ↓
Done!
```

## Configuration

Set in `.env`:
- `GROQ_API_KEY` - Your Groq API key
- `GROQ_MODEL` - Model to use (default: llama-3.3-70b-versatile)

## Memory Storage

Agent memory is stored in `Agents/agent_memory.json`:
- Conversation history
- Action logs
- Learned patterns

## Integration with Existing System

The agentic system integrates seamlessly:
- Uses existing `GroqSummarizer`
- Uses existing `email_classifier`
- Works with `GmailConnector` and `OutlookConnector`
- Can be called from `server.py` MCP tools

## Example: Adding to MCP Server

```python
# In server.py
from Agents.email_agent import EmailAgent
from Agents.agent_tools import AgentTools

agent = EmailAgent()
tools = AgentTools()

@mcp.tool("agent_process_email")
def agent_process_email(email_id: str, source: str):
    # Fetch email
    if source == "gmail":
        email = gmail.get_thread_text(email_id)
    else:
        email = outlook.get_thread_text(email_id)
    
    # Process through agent
    result = agent.process_email(email, tools.get_all_tools())
    return result
```

## Next Steps

To make it even more agentic:

1. **Add More Tools**:
   - Send email replies
   - Create calendar events
   - Add to task lists

2. **Enhanced Memory**:
   - Long-term memory with embeddings
   - User preference learning

3. **Multi-Agent System**:
   - Specialized agents for different tasks
   - Agent coordination

4. **Action Execution**:
   - Actually send replies
   - Update email labels
   - Create calendar events

## Files

- `email_agent.py` - Core agent with ReAct loop
- `agent_tools.py` - Tool implementations
- `agent_orchestrator.py` - Orchestrator for autonomous operation
- `example_usage.py` - Usage examples
- `agent_memory.json` - Agent's memory (auto-created)

