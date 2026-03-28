import logging

from fastapi import HTTPException, APIRouter
from pydantic import BaseModel

from services.meeting import update_meeting_config, set_bot_active, get_active_bot_meet_ids
from services.recallai_api import leave_recall_bot
from services.meeting import get_meeting

router = APIRouter(prefix="/meeting")

class ConfigPayload(BaseModel):
    jira_key: str | None = None
    # Możesz tu dodawać kolejne pola w przyszłości, np. prompt_mode: str | None = None


@router.post("/{meet_id}/config")
async def update_config(meet_id: str, payload: ConfigPayload):
    """
    Zapisuje/aktualizuje konfigurację dla konkretnego spotkania.
    """
    config_data = payload.model_dump(exclude_unset=True)

    success = update_meeting_config(meet_id, config_data)
    if not success:
        raise HTTPException(status_code=404, detail="Meeting not found in DB")

    logging.info(f"[CONFIG] Zaktualizowano konfigurację dla {meet_id}: {config_data.keys()}")
    return {"status": "success", "message": "Konfiguracja zapisana."}


@router.delete("/{meet_id}/bot")
async def remove_bot(meet_id: str):
    """
    Endpoint usuwający bota ze spotkania.
    """
    meeting = get_meeting(meet_id)

    if not meeting or not meeting.get("active_bot"):
        raise HTTPException(status_code=404, detail="No active bot found for this meeting")
    bot_id_to_remove = meeting.get("bot_id")

    if not bot_id_to_remove:
        raise HTTPException(status_code=404, detail="Bot ID is missing in database for this meeting")

    success = await leave_recall_bot(bot_id_to_remove)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to make bot leave via Recall API")

    set_bot_active(meet_id, is_active=False)

    return {"status": "success", "message": "Bot opuścił spotkanie."}