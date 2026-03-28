import argparse
import sys
from pathlib import Path


def _configure_import_path() -> None:
    src_path = Path(__file__).resolve().parent / 'src'
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Transcript pipeline: create doc -> write text -> fact-check -> summarize'
    )
    parser.add_argument('--title', default='Meeting Transcript Pipeline', help='Title for transcript doc')
    parser.add_argument('--text', help='Transcript text input. If missing, input is requested interactively.')
    return parser.parse_args()


def _get_text_input(arg_text: str | None) -> str:
    if arg_text and arg_text.strip():
        return arg_text.strip()

    print('Paste transcript text. Finish with an empty line:')
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)

    text = '\n'.join(lines).strip()
    if not text:
        raise ValueError('No transcript text provided.')
    return text


def _append_live_fact_checks(doc_id: str, transcript_text: str, live_fact_check, append_text_to_doc) -> None:
    notes = []
    for line in transcript_text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue

        result = live_fact_check(clean_line)
        if result:
            notes.append(f'- "{clean_line}" -> {result}')

    if notes:
        block = 'Live Fact-Check Notes\n' + '\n'.join(notes)
        append_text_to_doc(doc_id, '\n' + block)


def main():
    _configure_import_path()

    from docsBot import create_and_share_doc, append_text_to_doc  
    from fact_checker import live_fact_check  
    from post_meeting_analyzer import batch_fact_check_doc  
    from summarizer import process_meeting  

    args = _parse_args()
    transcript_text = _get_text_input(args.text)

    print('1) Creating transcript document...')
    transcript_doc_id, transcript_link = create_and_share_doc(args.title)
    if not transcript_doc_id:
        raise RuntimeError('Failed to create transcript document.')

    print('2) Writing transcript input...')
    append_text_to_doc(transcript_doc_id, transcript_text)

    print('3) Running live line-by-line fact-check...')
    _append_live_fact_checks(transcript_doc_id, transcript_text, live_fact_check, append_text_to_doc)

    print('4) Running full-document fact-check annotations...')
    batch_fact_check_doc(transcript_doc_id)

    print('5) Creating final summary document...')
    process_meeting(transcript_doc_id)

    print('\nPipeline completed.')
    print(f'Transcript doc: {transcript_link}')


if __name__ == "__main__":
    main()
