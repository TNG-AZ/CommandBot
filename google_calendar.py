import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
creds = None


def get_events(pull_count=10):
    global creds
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES)
    try:
        service = build('calendar', 'v3', credentials=creds)

        # Call the Calendar API
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print('Getting the upcoming 10 events')
        events_result = service.events().list(calendarId='tng.az.board@gmail.com', timeMin=now,
                                              maxResults=pull_count, singleEvents=True,
                                              orderBy='startTime').execute()
        return events_result.get('items', [])
    except HttpError as error:
        print('An error occurred: %s' % error)