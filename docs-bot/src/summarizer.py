import os
from google import genai
from dotenv import load_dotenv
from googleapiclient.discovery import build

from docsBot import authenticate_google, create_and_share_doc, append_text_to_doc

load_dotenv()

def read_doc_text(doc_id):
    creds = authenticate_google()
    docs_service = build('docs', 'v1', credentials=creds)
    
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get('body').get('content')
    
    full_text = ""
    for structural_element in content:
        if 'paragraph' in structural_element:
            for element in structural_element.get('paragraph').get('elements'):
                if 'textRun' in element:
                    full_text += element.get('textRun').get('content')
                    
    return full_text.strip()

def generate_gemini_summary(transcript_text):
    client = genai.Client()
    
    prompt = f"""
    You are an expert executive assistant. Read the meeting transcript and return concise markdown-like text.

    Formatting requirements:
    - Start with: # Meeting Summary
    - Add section: ## Overview (2-3 sentences)
    - Add section: ## Key Takeaways (use '-' bullets)
    - Add section: ## Action Items (use '-' bullets, include owner when possible)
    - If no action items exist, add '- None identified.'
    
    Transcript:
    {transcript_text}
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=prompt
    )
    
    return response.text

def process_meeting(transcript_doc_id):
    transcript = read_doc_text(transcript_doc_id)
    
    if not transcript:
        return {
            'processed': False,
            'reason': 'empty_transcript',
            'summaryDocId': None,
            'summaryDocLink': None,
        }
        
    summary_text = generate_gemini_summary(transcript)
    
    summary_id, summary_link = create_and_share_doc("Meeting Summary & Action Items")
    if not summary_id:
        return {
            'processed': False,
            'reason': 'summary_doc_create_failed',
            'summaryDocId': None,
            'summaryDocLink': None,
        }
    
    append_text_to_doc(summary_id, summary_text)
    return {
        'processed': True,
        'summaryDocId': summary_id,
        'summaryDocLink': summary_link,
    }
    
