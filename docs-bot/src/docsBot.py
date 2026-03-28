import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate_google():
    creds = None
    
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return creds

def create_and_share_doc(doc_title="My Python Hackathon Doc"):
    try:
        creds = authenticate_google()
        
        drive_service = build('drive', 'v3', credentials=creds)

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

        permission = {
            'type': 'anyone',
            'role': 'writer'
        }
        
        drive_service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id'
        ).execute()


        
        return file_id,doc_link

    except Exception as e:
        return None

def append_text_to_doc(doc_id, text_to_insert):
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

