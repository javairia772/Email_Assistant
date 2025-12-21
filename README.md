# Email Assistant

A comprehensive email management and summarization system that integrates with Gmail and Outlook, providing AI-powered email processing and organization.

## 🌟 Features

- **Dual Email Integration**
  - Seamless connection with Gmail and Outlook accounts
  - Unified interface for managing emails from both services

- **AI-Powered Summarization**
  - Automatic summarization of email threads
  - Contact-specific conversation history
  - Smart categorization of emails

- **Smart Features**
  - Email classification by importance and role
  - Automated follow-up scheduling
  - Action item extraction
  - Calendar integration for meeting scheduling

- **Dashboard**
  - Interactive web interface
  - Email thread visualization
  - Quick actions and replies

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- Google Cloud Platform (GCP) project with Gmail API enabled
- Microsoft Azure App Registration for Outlook integration
- Groq API key for AI summarization

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/email-assistant.git
   cd email-assistant
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the root directory with the following variables:
   ```
   # Gmail API
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   
   # Microsoft Graph API
   OUTLOOK_CLIENT_ID=your_outlook_client_id
   OUTLOOK_CLIENT_SECRET=your_outlook_client_secret
   OUTLOOK_TENANT_ID=your_tenant_id
   
   # Groq API
   GROQ_API_KEY=your_groq_api_key
   
   # Application
   SECRET_KEY=your_secret_key
   ```

## 🏃‍♂️ Running the Application

1. Start the main server:
   ```bash
   python server.py
   ```

2. Start the dashboard server in a new terminal:
   ```bash
   python dashboard_server.py
   ```

3. Start the auto-summarizer (optional):
   ```bash
   python auto_summarizer_loop.py
   ```

4. Access the web interface at `http://localhost:8000`

## 🔐 Authentication Setup

### Gmail API Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Gmail API
4. Create OAuth 2.0 credentials
5. Download the credentials JSON file as `credentials.json`

### Outlook API Setup
1. Go to [Microsoft Azure Portal](https://portal.azure.com/)
2. Register a new application
3. Add API permissions for `Mail.Read`, `Mail.Send`, `Calendars.ReadWrite`
4. Generate a client secret
5. Add `http://localhost:8000/auth/outlook/callback` as a redirect URI
