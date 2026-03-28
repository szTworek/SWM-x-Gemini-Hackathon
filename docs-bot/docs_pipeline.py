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
        ACTIVE_DOC_ID, transcript_link = create_and_share_doc('Live Meeting Transcript Pipeline')

    append_text_to_doc(ACTIVE_DOC_ID, formatted_line)



def trigger_post_meeting_pipeline() -> None:
    global ACTIVE_DOC_ID
    
    if not ACTIVE_DOC_ID:
        return

    batch_fact_check_doc(ACTIVE_DOC_ID)

    process_meeting(ACTIVE_DOC_ID)

    ACTIVE_DOC_ID = None 