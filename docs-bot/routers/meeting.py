from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.pipeline import pipeline_service

router = APIRouter(prefix='/meeting')


class StartMeetingRequest(BaseModel):
    title: str | None = None
    chatWebhookUrl: str | None = None


class TranscriptLineRequest(BaseModel):
    participantName: str = 'Unknown'
    text: str
    isFinal: bool = True


class EndMeetingResponse(BaseModel):
    meetId: str
    processed: bool
    transcriptDocId: str | None = None
    transcriptDocLink: str | None = None
    summaryDocId: str | None = None
    summaryDocLink: str | None = None
    reason: str | None = None


@router.post('/{meet_id}/start')
async def start_meeting(meet_id: str, payload: StartMeetingRequest | None = None):
    try:
        return pipeline_service.start_meeting(
            meet_id,
            payload.title if payload else None,
            payload.chatWebhookUrl if payload else None,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post('/{meet_id}/transcript')
async def add_transcript_line(meet_id: str, payload: TranscriptLineRequest):
    try:
        return pipeline_service.add_transcript_line(
            meet_id=meet_id,
            participant_name=payload.participantName,
            text=payload.text,
            is_final=payload.isFinal,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get('/{meet_id}/status')
async def get_status(meet_id: str):
    return pipeline_service.status(meet_id)


@router.post('/{meet_id}/end', response_model=EndMeetingResponse)
async def end_meeting(meet_id: str):
    try:
        result = pipeline_service.end_meeting(meet_id)
        if not result.get('processed'):
            raise HTTPException(status_code=404, detail=result.get('reason', 'meeting_not_started'))
        return result
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post('/webhook/recall')
async def recall_webhook(payload: dict):
    event = payload.get('event')

    if event not in ('transcript.data', 'transcript.partial_data'):
        return {'status': 'ok', 'ignored': True}

    data_root = payload.get('data', {})
    data_block = data_root.get('data', {})

    meet_id = data_root.get('meeting_id') or payload.get('meetId') or payload.get('meetingId')
    if not meet_id:
        raise HTTPException(status_code=400, detail='meeting_id is required in webhook payload')

    words = data_block.get('words', [])
    participant = data_block.get('participant', {})
    participant_name = participant.get('name', 'Unknown')

    text_parts = [word.get('text', '') for word in words if isinstance(word, dict)]
    full_text = ''.join(text_parts).strip() or ' '.join(text_parts).strip()

    try:
        result = pipeline_service.add_transcript_line(
            meet_id=meet_id,
            participant_name=participant_name,
            text=full_text,
            is_final=(event == 'transcript.data'),
        )
        return {'status': 'ok', 'event': event, 'result': result}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
