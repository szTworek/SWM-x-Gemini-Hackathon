import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']


def _normalize_lines(text: str):
    normalized = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    rows = []

    for raw_line in normalized.split('\n'):
        stripped = raw_line.strip()

        if not stripped:
            rows.append({'text': '', 'kind': 'blank'})
            continue

        if stripped.startswith('# '):
            rows.append({'text': stripped[2:].strip(), 'kind': 'h1'})
        elif stripped.startswith('## '):
            rows.append({'text': stripped[3:].strip(), 'kind': 'h2'})
        elif stripped.startswith('- '):
            rows.append({'text': stripped[2:].strip(), 'kind': 'bullet'})
        else:
            rows.append({'text': stripped, 'kind': 'normal'})

    return rows


def _build_style_requests(start_index: int, rows: list[dict]):
    requests = []
    cursor = start_index

    for row in rows:
        line = row['text']
        line_start = cursor
        line_end = cursor + len(line)

        if line:
            if row['kind'] == 'h1':
                requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': line_start, 'endIndex': line_end},
                        'paragraphStyle': {'namedStyleType': 'HEADING_1'},
                        'fields': 'namedStyleType'
                    }
                })
            elif row['kind'] == 'h2':
                requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': line_start, 'endIndex': line_end},
                        'paragraphStyle': {'namedStyleType': 'HEADING_2'},
                        'fields': 'namedStyleType'
                    }
                })
            elif row['kind'] == 'bullet':
                requests.append({
                    'createParagraphBullets': {
                        'range': {'startIndex': line_start, 'endIndex': line_end},
                        'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
                    }
                })

            colon_index = line.find(':')
            if 0 < colon_index <= 40:
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': line_start,
                            'endIndex': line_start + colon_index + 1,
                        },
                        'textStyle': {'bold': True},
                        'fields': 'bold'
                    }
                })

        cursor += len(line) + 1

    return requests

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
    rows = _normalize_lines(text_to_insert)
    rendered = "\n".join(row['text'] for row in rows).strip('\n')
    if not rendered:
        return

    creds = authenticate_google() 
    docs_service = build('docs', 'v1', credentials=creds)

    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get('body', {}).get('content', [])
    insert_index = body_content[-1].get('endIndex', 1) - 1 if body_content else 1

    insert_text = f"{rendered}\n"

    requests = [{
        'insertText': {
            'location': {'index': insert_index},
            'text': insert_text,
        }
    }]

    requests.extend(_build_style_requests(insert_index, rows))

    docs_service.documents().batchUpdate(
        documentId=doc_id, 
        body={'requests': requests}
    ).execute()

