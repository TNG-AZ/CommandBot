import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_events(pull_count=10):
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.

    If you don't have credentials, follow the guide at https://medium.com/iceapple-tech-talks/integration-with-google-calendar-api-using-service-account-1471e6e102c8 up to the point where it asks you to go to admin.google.com.
    Instead of doing that, select the service account you created, go to "keys", click "create new key", choose "json", and it will download the file you need.
    """
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES)
    try:
        service = build('calendar', 'v3', credentials=creds)

        # Call the Calendar API
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print(f'Getting the upcoming {pull_count} events')
        events_result = service.events().list(calendarId='tng.az.board@gmail.com', timeMin=now,
                                              maxResults=pull_count, singleEvents=True,
                                              orderBy='startTime').execute()
        return events_result.get('items', [])
    except HttpError as error:
        print('An error occurred: %s' % error)
        
