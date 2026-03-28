from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict


def _configure_import_path() -> None:
    src_path = Path(__file__).resolve().parent.parent / 'src'
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


_configure_import_path()

from docsBot import create_and_share_doc, append_text_to_doc  # type: ignore[import-not-found]
from fact_checker import live_fact_check  # type: ignore[import-not-found]
from post_meeting_analyzer import batch_fact_check_doc  # type: ignore[import-not-found]
from summarizer import process_meeting  # type: ignore[import-not-found]


class MeetingPipelineService:
    def __init__(self) -> None:
        self._active_doc_ids: Dict[str, str] = {}
        self._active_doc_links: Dict[str, str] = {}

    def start_meeting(self, meet_id: str, title: str | None = None) -> dict:
        if meet_id in self._active_doc_ids:
            return {
                'meetId': meet_id,
                'docId': self._active_doc_ids[meet_id],
                'docLink': self._active_doc_links[meet_id],
                'alreadyStarted': True,
            }

        doc_title = title or f'Live Meeting Transcript {meet_id}'
        doc_id, doc_link = create_and_share_doc(doc_title)
        if not doc_id:
            raise RuntimeError('Failed to create transcript document.')

        self._active_doc_ids[meet_id] = doc_id
        self._active_doc_links[meet_id] = doc_link
        return {
            'meetId': meet_id,
            'docId': doc_id,
            'docLink': doc_link,
            'alreadyStarted': False,
        }

    def add_transcript_line(self, meet_id: str, participant_name: str, text: str, is_final: bool) -> dict:
        if not is_final:
            return {'meetId': meet_id, 'written': False, 'reason': 'partial_transcript'}

        clean_text = (text or '').strip()
        if not clean_text:
            return {'meetId': meet_id, 'written': False, 'reason': 'empty_text'}

        if meet_id not in self._active_doc_ids:
            self.start_meeting(meet_id)

        doc_id = self._active_doc_ids[meet_id]
        speaker = (participant_name or 'Unknown').strip()
        line = f'{speaker}: {clean_text}'

        append_text_to_doc(doc_id, line)

        fact_note = live_fact_check(line)
        if fact_note:
            append_text_to_doc(doc_id, f'    ↳ AI Fact Check: {fact_note}')

        return {'meetId': meet_id, 'written': True, 'docId': doc_id, 'docLink': self._active_doc_links[meet_id]}

    def end_meeting(self, meet_id: str) -> dict:
        doc_id = self._active_doc_ids.get(meet_id)
        if not doc_id:
            return {'meetId': meet_id, 'processed': False, 'reason': 'meeting_not_started'}

        batch_fact_check_doc(doc_id)
        process_meeting(doc_id)

        transcript_link = self._active_doc_links.pop(meet_id)
        self._active_doc_ids.pop(meet_id, None)

        return {
            'meetId': meet_id,
            'processed': True,
            'transcriptDocId': doc_id,
            'transcriptDocLink': transcript_link,
        }

    def status(self, meet_id: str) -> dict:
        doc_id = self._active_doc_ids.get(meet_id)
        return {
            'meetId': meet_id,
            'active': bool(doc_id),
            'docId': doc_id,
            'docLink': self._active_doc_links.get(meet_id),
        }


pipeline_service = MeetingPipelineService()
