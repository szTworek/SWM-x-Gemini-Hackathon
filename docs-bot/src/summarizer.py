import os
from google import genai
from dotenv import load_dotenv
from googleapiclient.discovery import build

from docsBot import authenticate_google, create_and_share_doc, append_text_to_doc

load_dotenv()

def read_doc_text(doc_id):
    """Extracts all text from a Google Document."""
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
    """Sends the transcript to Gemini using the new SDK."""
    client = genai.Client()
    
    prompt = f"""
    You are an expert executive assistant. Please read the following meeting transcript and provide a highly structured summary.
    
    Include:
    1. A brief 2-3 sentence overview of what was discussed.
    2. Key Takeaways (bullet points).
    3. Action Items (who needs to do what, if mentioned).
    
    Transcript:
    {transcript_text}
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=prompt
    )
    
    return response.text

def process_meeting(transcript_doc_id):
    """The main workflow: Read -> Summarize -> Save."""
    print("1. Reading transcript from Google Docs...")
    transcript = read_doc_text(transcript_doc_id)
    
    if not transcript:
        print("Error: The transcript document is empty!")
        return
        
    print("2. Analyzing text with Gemini...")
    summary_text = generate_gemini_summary(transcript)
    
    print("3. Creating a new Google Doc for the summary...")
    summary_id, summary_link = create_and_share_doc("Meeting Summary & Action Items")
    
    print("4. Writing AI summary into the new document...")
    append_text_to_doc(summary_id, summary_text)
    
    print("\nAll Done! Here is your AI Meeting Summary:")
    print(f"Link: {summary_link}")
