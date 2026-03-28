import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate_google():
    """Handles OAuth2 authentication and auto-refreshes the token."""
    creds = None
    
    if os.path.exists('token.json'):
        print("Loading saved credentials from token.json...")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired. Auto-refreshing in the background...")
            creds.refresh(Request())
        else:
            print("No valid token found. Opening browser for login...")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            print("New token saved securely!")
            
    return creds

def create_and_share_doc(doc_title="My Python Hackathon Doc"):
    """Creates a Google Doc and returns an editable share link."""
    try:
        creds = authenticate_google()
        
        drive_service = build('drive', 'v3', credentials=creds)

        print("\nCreating document...")
        file_metadata = {
            'name': doc_title,
            'mimeType': 'application/vnd.google-apps.document'
        }
        
        file = drive_service.files().create(
            body=file_metadata, 
            fields='id, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        doc_link = file.get('webViewLink')

        print("Setting permissions to 'Anyone can edit'...")
        permission = {
            'type': 'anyone',
            'role': 'writer'
        }
        
        drive_service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id'
        ).execute()

        print("\nSuccess!")
        print(f"Edit Link: {doc_link}\n")
        
        return file_id,doc_link

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        return None

def append_text_to_doc(doc_id, text_to_insert):
    """Appends formatted text to the very bottom of a Google Doc."""
    creds = authenticate_google() 
    
    docs_service = build('docs', 'v1', credentials=creds)

    requests = [
        {
            'insertText': {
                'endOfSegmentLocation': {
                    'segmentId': '' 
                },
                'text': f"{text_to_insert}\n" 
            }
        }
    ]

    docs_service.documents().batchUpdate(
        documentId=doc_id, 
        body={'requests': requests}
    ).execute()

if __name__ == '__main__':
    create_and_share_doc("SWM Hackathon Auto-Doc")