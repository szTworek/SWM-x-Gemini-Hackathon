import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
import logging
import random
from typing import Dict, List
from services.meeting import create_meeting_if_not_exists, get_meeting, set_bot_active
from services.recallai_api import create_recall_bot, send_chat_message, get_chat_messages
from services.docs_bot_api import start_meeting_pipeline, forward_recall_transcript, get_pipeline_status

router = APIRouter(prefix="/meeting")

active_connections: Dict[str, List[WebSocket]] = {}
active_runners: Dict[str, asyncio.Task] = {}


def _run_background(coro, label: str):
    task = asyncio.create_task(coro)

    def _done_callback(done_task: asyncio.Task):
        try:
            done_task.result()
        except Exception as error:
            logging.warning(f"[BACKGROUND:{label}] failed: {error}")

    task.add_done_callback(_done_callback)
    return task


async def _start_docs_pipeline_and_share_link(meet_id: str, bot_id: str):
    docs_result = await start_meeting_pipeline(
        meet_id,
        title=f"Meeting {meet_id} - Live Transcript",
    )
    transcript_link = docs_result.get("docLink") if docs_result else None
    if transcript_link:
        await send_chat_message(bot_id, f"Live transcript: {transcript_link}")

async def meet_runner(meet_id):
    print(f"[Runner] Starting task for meeting: {meet_id}")
    while True:
        await asyncio.sleep(5)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_meet_id = None

    try:
        while True:
            data = await websocket.receive_json()
            meet_id = data.get("meetId")

            if meet_id:
                current_meet_id = meet_id

                is_new = create_meeting_if_not_exists(meet_id)
                if is_new:
                    print(f"Created new meeting record in the database (file): {meet_id}")

                if meet_id not in active_connections:
                    active_connections[meet_id] = []

                if websocket not in active_connections[meet_id]:
                    active_connections[meet_id].append(websocket)

                print(f"Client connected to meeting: {meet_id}")

                if meet_id not in active_runners:
                    active_runners[meet_id] = asyncio.create_task(meet_runner(meet_id))

    except WebSocketDisconnect:
        if current_meet_id and current_meet_id in active_connections:
            if websocket in active_connections[current_meet_id]:
                active_connections[current_meet_id].remove(websocket)


@router.post("/{meet_id}/bot")
async def create_bot(meet_id: str):
    meeting = get_meeting(meet_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.get("active_bot") is True:
        raise HTTPException(status_code=400, detail="Bot is already active for this meeting")

    try:
        recall_response = await create_recall_bot(meet_id)
        bot_id = recall_response.get("id")
        print(f"Created Recall.ai bot with ID: {bot_id}")
    except Exception as e:
        raise e

    set_bot_active(meet_id=meet_id, bot_id=bot_id, is_active=True)

    _run_background(_start_docs_pipeline_and_share_link(meet_id, bot_id), f"docs-start-{meet_id}")

    return {
        "message": "Bot creation process started",
        "bot_id": bot_id,
        "docs_pipeline": {"status": "starting_async"},
    }


@router.get("/{meet_id}/docs-status")
async def docs_status(meet_id: str):
    status = await get_pipeline_status(meet_id)
    if not status:
        raise HTTPException(status_code=502, detail="docs-bot unavailable")
    return status


@router.post("/webhook/recall")
async def recall_webhook(payload: dict):
    event = payload.get("event")

    if event in ("transcript.data", "transcript.partial_data"):
        _run_background(forward_recall_transcript(payload), f"docs-forward-{event}")

    if event in ("transcript.data", "transcript.partial_data"):
        data_block = payload.get("data", {}).get("data", {})
        words = data_block.get("words", [])
        participant = data_block.get("participant", {})

        text_parts = [w.get("text", "") for w in words]

        full_text = "".join(text_parts).strip()
        if not full_text:
            full_text = " ".join(text_parts).strip()

        participant_name = participant.get("name", "Unknown")
        finality = "[FINAL]" if event == "transcript.data" else "[PART_]"

        if full_text:
            print(f"[{event}] {finality} {participant_name}: {full_text}")

    return {"status": "ok"}


import base64
from services.agent_service import AgentService
from routers.bot_media import bot_audio_queues

gemini_active_state: Dict[str, bool] = {}
active_agents: Dict[str, AgentService] = {}
agent_receive_tasks: Dict[str, asyncio.Task] = {}


async def consume_agent_responses(meet_id: str, agent: AgentService):
    if meet_id not in bot_audio_queues:
        bot_audio_queues[meet_id] = asyncio.Queue()

    print(f"[AGENT CONSUMER] Starting receiver task for {meet_id}")
    try:
        async for chunk in agent.receive_responses():
            # Responses are returned as raw PCM bytes. We push them directly
            # into the outbound queue so the Sandbox HTML can play them instantly!
            bot_audio_queues[meet_id].put_nowait(chunk)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[AGENT CONSUMER] Event stream ended/error for {meet_id}: {e}")
    finally:
        print(f"[AGENT CONSUMER] Receiver task ended for {meet_id}")



@router.post("/{meet_id}/toggle-gemini")
async def toggle_gemini(meet_id: str):
    current = gemini_active_state.get(meet_id, False)
    new_state = not current
    gemini_active_state[meet_id] = new_state

    if new_state:
        status_str = "ON"
        if meet_id not in active_agents:

            async def broadcast_tool_event(tool_id: str, tool_name: str, log: str):
                """Forwards tool_update events to all WebSocket clients for this meeting."""
                message = {
                    "event": "tool_update",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "log": log,
                }
                for ws in list(active_connections.get(meet_id, [])):
                    try:
                        await ws.send_json(message)
                    except Exception as e:
                        logging.warning(f"[WS BROADCAST] Failed to send tool event: {e}")

            async def chat_callback(payload: str, is_text: bool = False):
                """
                Sends either a plain text message or a chart image to the Meet chat.
                - is_text=True  → plain text message sent directly to chat
                - is_text=False → payload is a base64 PNG; we send a short notice
                  (Google Meet chat doesn't support image attachments, so we send
                   a text summary and log the chart for the extension)
                """
                meeting = get_meeting(meet_id)
                bot_id = meeting.get("bot_id") if meeting else None
                if not bot_id:
                    logging.warning(f"[CHAT] No active bot_id for meeting {meet_id}, cannot send chat message.")
                    return

                if is_text:
                    await send_chat_message(bot_id, payload)
                else:
                    # Google Meet chat doesn't support images — send a text notice and
                    # forward the base64 chart to the extension panel via WebSocket
                    notice = "📊 A chart has been generated. Check the SWM Assistant panel to view it."
                    await send_chat_message(bot_id, notice)

                    # Also push the chart to the extension via WebSocket as a special event
                    chart_event = {
                        "event": "agent_chart",
                        "image_b64": payload,
                    }
                    for ws in list(active_connections.get(meet_id, [])):
                        try:
                            await ws.send_json(chart_event)
                        except Exception as e:
                            logging.warning(f"[WS BROADCAST] Failed to send chart event: {e}")

            async def get_chat_messages_callback(limit: int = 10) -> list:
                """Fetches the last N chat messages for the active bot in this meeting."""
                meeting = get_meeting(meet_id)
                bot_id = meeting.get("bot_id") if meeting else None
                if not bot_id:
                    return []
                return await get_chat_messages(bot_id, limit=limit)

            agent = AgentService(
                tool_event_callback=broadcast_tool_event,
                chat_callback=chat_callback,
                get_chat_messages_callback=get_chat_messages_callback,
            )
            await agent.start_session()
            active_agents[meet_id] = agent
            agent_receive_tasks[meet_id] = asyncio.create_task(consume_agent_responses(meet_id, agent))
    else:
        status_str = "OFF"
        if meet_id in active_agents:
            agent = active_agents.pop(meet_id)
            task = agent_receive_tasks.pop(meet_id, None)
            if task:
                task.cancel()
            await agent.close_session()

    print(f"\n[🚀 REACTING] Changed Gemini Live sending mode to: {status_str} for {meet_id}\n")
    return {"meet_id": meet_id, "sending_to_gemini": new_state}



import time
from io import BytesIO
from PIL import Image

@router.websocket("/ws/recall-media/{meet_id}")
async def recall_media_websocket(websocket: WebSocket, meet_id: str):
    await websocket.accept()
    print(f"[MEDIA-WS] Established stream connection for meeting {meet_id}")

    frame_count: int = 0
    last_video_send_time = 0.0

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("event")
            is_gemini_on = gemini_active_state.get(meet_id, False)

            if event_type == "audio_mixed_raw.data":
                b64_buffer = payload.get("data", {}).get("data", {}).get("buffer", "")
                if b64_buffer and is_gemini_on and meet_id in active_agents:
                    audio_bytes = base64.b64decode(b64_buffer)
                    await active_agents[meet_id].send_audio_chunk(audio_bytes)
                    if frame_count % 100 == 0:
                        print(f"[MEDIA-WS -> GEMINI] Pushing audio stream... (packet {frame_count})")
                    frame_count += 1

            elif event_type == "video_separate_png.data":
                b64_buffer = payload.get("data", {}).get("data", {}).get("buffer", "")
                if b64_buffer and is_gemini_on and meet_id in active_agents:
                    current_time = time.time()
                    # Rate limit to 1 frame every 2 seconds.
                    # Video tokens are VERY expensive in the Live API context window.
                    # At 1fps + audio, the session was dying after ~1 minute.
                    if current_time - last_video_send_time >= 2.0:
                        png_bytes = base64.b64decode(b64_buffer)
                        
                        # Resize and compress to JPEG to prevent Google API WebSocket 1011 payload crashes
                        img = Image.open(BytesIO(png_bytes))
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                        
                        # Gemini doesn't need 1080p. 640px is plenty for vision analysis!
                        img.thumbnail((640, 640))
                        
                        out_io = BytesIO()
                        img.save(out_io, format="JPEG", quality=80)
                        jpeg_bytes = out_io.getvalue()
                        
                        await active_agents[meet_id].send_video_frame(jpeg_bytes, mime_type="image/jpeg")
                        last_video_send_time = current_time
                        if frame_count % 100 == 0:
                            print(f"[MEDIA-WS -> GEMINI] Pushing video frame (JPEG compress)... (packet {frame_count})")
                    frame_count += 1

    except WebSocketDisconnect:
        print("[MEDIA-WS] Connection closed by Recall.ai client")
    except Exception as e:
        print(f"[MEDIA-WS] Stream exception: {e}")
    finally:
        print(f"[MEDIA-WS] Stream gracefully closed for meeting {meet_id}")

