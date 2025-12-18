"""
Google Calendar integration for the Email Assistant.
Handles scheduling events based on email content.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the token.pickle file
SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_PATH = 'token_calendar.pickle'

class GoogleCalendar:
    def __init__(self, credentials_path: str = 'credentials.json'):
        """Initialize Google Calendar API client."""
        self.creds = None
        self.credentials_path = credentials_path
        self.service = self._get_calendar_service()

    def _get_calendar_service(self):
        """Get authenticated Google Calendar API service."""
        # The file token.pickle stores the user's access and refresh tokens
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, 'rb') as token:
                self.creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Failed to refresh token: {e}")
                    self.creds = None
            
            if not self.creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path,
                        SCOPES,
                        redirect_uri='http://localhost:8080/'
                    )
                    self.creds = flow.run_local_server(port=8080, open_browser=True)
                    
                    # Save the credentials for the next run
                    with open(TOKEN_PATH, 'wb') as token:
                        pickle.dump(self.creds, token)
                        
                except Exception as e:
                    logger.error(f"Authentication failed: {e}")
                    raise

        return build('calendar', 'v3', credentials=self.creds)

    def _parse_date_time(self, date_str: str, time_str: str = None) -> tuple:
        """Parse date and time strings into datetime objects."""
        from dateutil import parser
        
        try:
            # Try to parse the date string with dateutil
            if time_str:
                dt = parser.parse(f"{date_str} {time_str}")
            else:
                dt = parser.parse(date_str)
                
            # If no time was provided, default to current time
            if not time_str:
                now = datetime.now()
                dt = dt.replace(hour=now.hour, minute=now.minute)
                
            # Ensure the datetime is timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                
            return dt
            
        except Exception as e:
            logger.warning(f"Failed to parse date/time: {str(e)}")
            return None

    def extract_meeting_info(self, email_body: str) -> Optional[Dict[str, Any]]:
        """Extract meeting information from email body.
        
        Args:
            email_body: The content of the email
            
        Returns:
            Dict containing meeting details or None if no meeting found
        """
        # More comprehensive date patterns
        date_patterns = [
            # MM/DD/YYYY or DD/MM/YYYY
            r'(\b(?:0?[1-9]|1[0-2])[\/\-\.](?:0?[1-9]|[12][0-9]|3[01])[\/\-](?:\d{4}|\d{2})\b)',
            # Month name patterns
            r'(?:\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*\d{4})?)',
            # ISO format YYYY-MM-DD
            r'(\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01]))',
        ]
        
        # Time patterns (24h and 12h formats)
        time_patterns = [
            r'(\b(?:1[0-2]|0?[1-9]):[0-5][0-9]\s*(?:[AaPp][Mm])\b)',  # 12-hour with AM/PM
            r'(\b(?:[01]?[0-9]|2[0-3]):[0-5][0-9]\b)',  # 24-hour format
            r'(\b(?:1[0-2]|0?[1-9])\s*(?:[AaPp][Mm])\b)',  # 12-hour without minutes
        ]
        
        # Check for meeting-related keywords
        meeting_keywords = [
            'meeting', 'appointment', 'call', 'discussion', 'sync',
            'meet', 'schedule', 'calendar', 'event', 'reminder'
        ]
        
        # If no meeting-related keywords found, return None
        email_lower = email_body.lower()
        if not any(keyword in email_lower for keyword in meeting_keywords):
            return None
            
        # Try to extract date and time
        date_match = None
        time_match = None
        
        # Find the first date match
        for pattern in date_patterns:
            matches = list(re.finditer(pattern, email_body, re.IGNORECASE))
            if matches:
                # Prefer dates that are closer to meeting-related words
                for match in matches:
                    context = email_lower[max(0, match.start()-50):min(len(email_lower), match.end()+50)]
                    if any(word in context for word in meeting_keywords):
                        date_match = match
                        break
                if date_match:
                    break
                
                # If no date found near meeting words, take the first one
                date_match = matches[0]
                break
        
        if not date_match:
            return None
            
        # Look for time near the date match
        context_start = max(0, date_match.start() - 50)
        context_end = min(len(email_body), date_match.end() + 50)
        context = email_body[context_start:context_end]
        
        for pattern in time_patterns:
            time_matches = list(re.finditer(pattern, context, re.IGNORECASE))
            if time_matches:
                time_match = time_matches[0]  # Take the first time found near the date
                break
        
        # Parse the date and time
        event_time = self._parse_date_time(
            date_str=date_match.group().strip(),
            time_str=time_match.group().strip() if time_match else None
        )
        
        if not event_time:
            return None
            
        # Default to 1-hour duration
        end_time = event_time + timedelta(hours=1)
        
        # Create event details
        return {
            'date': date_match.group().strip(),
            'time': time_match.group().strip() if time_match else 'All Day',
            'summary': 'Meeting from Email',
            'description': 'Automatically created from email content\n\n---\n' + 
                         f'Extracted from email on {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            'start_time': event_time.isoformat(),
            'end_time': end_time.isoformat()
        }

    def create_event(self, event_details: Dict[str, Any], calendar_id: str = 'primary') -> Dict:
        """Create a calendar event.
        
        Args:
            event_details: Dictionary containing event details
            calendar_id: Calendar ID (default is 'primary' for primary calendar)
            
        Returns:
            Created event details or error message
        """
        try:
            event = {
                'summary': event_details.get('summary', 'New Event'),
                'description': event_details.get('description', 'Created by Email Assistant'),
                'start': {
                    'dateTime': event_details['start_time'],
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': event_details['end_time'],
                    'timeZone': 'UTC',
                },
            }
            
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            
            logger.info(f"Event created: {created_event.get('htmlLink')}")
            return {
                'success': True,
                'event_id': created_event['id'],
                'html_link': created_event.get('htmlLink', '')
            }
            
        except Exception as e:
            logger.error(f"Error creating calendar event: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def process_email_for_meetings(self, email_body: str, email_subject: str = '') -> Dict:
        """Process an email to find and schedule meetings.
        
        Args:
            email_body: The content of the email
            email_subject: Optional subject of the email
            
        Returns:
            Dictionary with results of the operation
        """
        meeting_info = self.extract_meeting_info(email_body)
        if not meeting_info:
            return {
                'success': False,
                'message': 'No meeting information found in email'
            }
            
        # Use email subject as event summary if available
        if email_subject:
            meeting_info['summary'] = email_subject
            
        # Create the calendar event
        return self.create_event(meeting_info)
