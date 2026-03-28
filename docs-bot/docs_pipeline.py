import sys
from pathlib import Path

def _configure_import_path() -> None:
    src_path = Path(__file__).resolve().parent / 'src'
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

_configure_import_path()

from docsBot import create_and_share_doc, append_text_to_doc  
from fact_checker import live_fact_check  
from post_meeting_analyzer import batch_fact_check_doc  
from summarizer import process_meeting  

ACTIVE_DOC_ID = None

def process_webhook_stream(participant_name: str, text: str, is_final: bool) -> None:
    global ACTIVE_DOC_ID

    if not is_final:
        return

    formatted_line = f"{participant_name}: {text}"

    if not ACTIVE_DOC_ID:
        print('\n1) Creating transcript document...')
        ACTIVE_DOC_ID, transcript_link = create_and_share_doc('Live Meeting Transcript Pipeline')
        print(f'Transcript doc created: {transcript_link}')

    print(f'2) Writing text: {formatted_line}')
    append_text_to_doc(ACTIVE_DOC_ID, formatted_line)

    print('3) Running live line-by-line fact-check...')
    result = live_fact_check(text)
    if result:
        note = f'    Live Fact-Check: {result}'
        print(note)
        append_text_to_doc(ACTIVE_DOC_ID, '\n' + note)

def trigger_post_meeting_pipeline() -> None:
    """Call this when the meeting is completely over to run the heavy batch tasks."""
    global ACTIVE_DOC_ID
    
    if not ACTIVE_DOC_ID:
        print("No active document found to process.")
        return

    print('\n4) Running full-document fact-check annotations...')
    batch_fact_check_doc(ACTIVE_DOC_ID)

    print('5) Creating final summary document...')
    process_meeting(ACTIVE_DOC_ID)

    print('\n🎉 Pipeline completely finished.')
    ACTIVE_DOC_ID = None 