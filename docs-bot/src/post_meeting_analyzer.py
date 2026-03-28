import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
from googleapiclient.discovery import build

from docsBot import authenticate_google

load_dotenv()

def batch_fact_check_doc(doc_id):
    print("1. Reading document and mapping paragraphs...")
    creds = authenticate_google()
    docs_service = build('docs', 'v1', credentials=creds)
    
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get('body').get('content')
    
    paragraphs = []
    full_transcript = ""
    
    for element in content:
        if 'paragraph' in element:
            para_text = ""
            for p_elem in element.get('paragraph').get('elements'):
                if 'textRun' in p_elem:
                    para_text += p_elem.get('textRun').get('content')
            
            clean_text = para_text.strip()
            if clean_text:
                full_transcript += clean_text + "\n"
                paragraphs.append({
                    'text': clean_text,
                    'end_index': element['endIndex']
                })

    if not full_transcript:
        print("Document is empty.")
        return

    print("2. Sending to Gemini for Fact-Checking (with Google Search)...")
    client = genai.Client()
    
    prompt = f"""
    You are a post-meeting fact-checker. 
    Read the following transcript. Identify any verifiable factual claims (e.g., dates, numbers, historical events, science, company facts).
    Use the Google Search tool to verify them.
    
    Return ONLY a raw JSON array of objects with this exact structure, and NO other text:
    [
        {{
            "exact_quote": "the exact sentence from the transcript that contains the claim",
            "fact_check": "Correction/Context: [Your search result]"
        }}
    ]
    
    If there are no factual claims, return an empty array [].
    
    Transcript:
    {full_transcript}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.1
        )
    )
    
    try:
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:] 
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        clean_json_string = raw_text.strip()
        
        fact_checks = json.loads(clean_json_string)
    except json.JSONDecodeError as e:
        print(f"Failed to parse Gemini's response as JSON: {e}")
        print("Raw response was:", response.text)
        return

    if not fact_checks:
        print("No factual claims needed checking! Document is clean.")
        return

    print(f"💡 Found {len(fact_checks)} facts to annotate. Preparing document updates...")

    insertions = []
    for item in fact_checks:
        quote = item.get("exact_quote", "")
        note = item.get("fact_check", "")
        
        for p in paragraphs:
            if quote in p['text'] or p['text'] in quote:
                insertions.append({
                    'index': p['end_index'],
                    'text': f"   AI Fact Check: {note}"
                })
                break 
                

    insertions.sort(key=lambda x: x['index'], reverse=True)

    if not insertions:
        print("Could not match quotes to the document. No changes made.")
        return

    print("4. Writing annotations directly into the Google Doc...")
    requests = []
    for insert in insertions:
        requests.append({
            'insertText': {
                'location': {
                    'index': insert['index'] - 1 
                },
                'text': "\n" + insert['text']
            }
        })

    docs_service.documents().batchUpdate(
        documentId=doc_id, 
        body={'requests': requests}
    ).execute()

    print("Success! Fact-checks have been injected right beneath the relevant lines.")

