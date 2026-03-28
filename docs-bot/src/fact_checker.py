import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def live_fact_check(transcript_line):
    """
    Evaluates a sentence. If it contains a factual claim, 
    it searches Google and returns context. Otherwise, returns None.
    """
    client = genai.Client()
    
    prompt = f"""
    You are a live meeting fact-checker and context provider.
    
    Analyze this spoken sentence from a meeting: 
    "{transcript_line}"
    
    Instructions:
    1. If the sentence contains a specific, verifiable claim (e.g., statistics, historical dates, company info, scientific claims), use the Google Search tool to find context or verify it.
    2. If it requires a fact-check or context, return a brief 1-2 sentence note starting with "Context:" or "Correction:".
    3. IMPORTANT: If the sentence is just casual conversation, opinions, greetings, or subjective thoughts (e.g., "I think we should do this", "Hello everyone"), reply EXACTLY with the word: SKIP
    """
    
    try:
        # We use gemini-2.5-flash because it is fast enough for live processing
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                # THIS IS THE MAGIC! It gives the model access to live Google Search
                tools=[{"google_search": {}}],
                temperature=0.1 # Keep it focused and analytical
            )
        )
        
        result = response.text.strip()
        
        # If Gemini decides it's just casual chat, we do nothing.
        if result == "SKIP" or result.startswith("SKIP"):
            return None
            
        return result
        
    except Exception as e:
        print(f"⚠️ Fact check failed: {e}")
        return None

# --- Quick Local Test ---
if __name__ == "__main__":
    print("Testing a casual sentence...")
    print(live_fact_check("Hey guys, thanks for joining the call today.")) 
    # Should print: None
    
    print("\nTesting a factual claim...")
    print(live_fact_check("I'm pretty sure Google was founded in 1995 by Elon Musk.")) 
    # Should print a correction based on a live Google Search!