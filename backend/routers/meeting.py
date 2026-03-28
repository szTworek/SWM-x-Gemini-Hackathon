import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Dict, List
from services.meeting import create_meeting_if_not_exists, get_meeting, set_bot_active
from services.recallai_api import create_recall_bot

router = APIRouter(prefix="/meeting")

active_connections: Dict[str, List[WebSocket]] = {}
active_runners: Dict[str, asyncio.Task] = {}


async def meet_runner(meet_id: str):
    print(f"[Runner] Starting task for meeting: {meet_id}")
    counter = 0
    try:
        while True:
            await asyncio.sleep(5)
            counter += 1
            message = f"Update #{counter} for room {meet_id}"

            if meet_id in active_connections:
                for ws in active_connections[meet_id].copy():
                    try:
                        await ws.send_json({"text": message})
                    except Exception:
                        if ws in active_connections[meet_id]:
                            active_connections[meet_id].remove(ws)
    except asyncio.CancelledError:
        print(f"[Runner] Stopped task for meeting: {meet_id}")


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

    set_bot_active(meet_id, True)

    return {"message": "Bot creation process started", "bot_id": bot_id}


@router.post("/webhook/recall")
async def recall_webhook(payload: dict):
    event = payload.get("event")

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


import wave
import uuid
import base64
import os

gemini_active_state: Dict[str, bool] = {}


@router.post("/{meet_id}/toggle-gemini")
async def toggle_gemini(meet_id: str):
    current = gemini_active_state.get(meet_id, False)
    gemini_active_state[meet_id] = not current
    status_str = "ON" if gemini_active_state[meet_id] else "OFF"
    print(f"\n[🚀 REACTING] Changed Gemini Live sending mode to: {status_str} for {meet_id}\n")
    return {"meet_id": meet_id, "sending_to_gemini": gemini_active_state[meet_id]}


@router.websocket("/ws/recall-media/{meet_id}")
async def recall_media_websocket(websocket: WebSocket, meet_id: str):
    await websocket.accept()
    print(f"[MEDIA-WS] Established stream connection for meeting {meet_id}")

    audio_filename = f"test_audio_{uuid.uuid4().hex[:6]}.wav"
    wave_file = wave.open(audio_filename, "wb")
    wave_file.setnchannels(1)
    wave_file.setsampwidth(2)
    wave_file.setframerate(16000)

    video_dir = f"test_video_{uuid.uuid4().hex[:6]}"
    os.makedirs(video_dir, exist_ok=True)
    frame_count: int = 0

    try:
        print(f"[MEDIA-WS] ---> Recording AUDIO to: {audio_filename} | Recording VIDEO to folder: {video_dir}/")

        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("event")

            is_gemini_on = gemini_active_state.get(meet_id, False)

            if event_type == "audio_mixed_raw.data":
                b64_buffer = payload.get("data", {}).get("data", {}).get("buffer", "")
                if b64_buffer:
                    audio_bytes = base64.b64decode(b64_buffer)
                    wave_file.writeframes(audio_bytes)

                    if is_gemini_on:
                        pass

            elif event_type == "video_separate_png.data":
                b64_buffer = payload.get("data", {}).get("data", {}).get("buffer", "")
                if b64_buffer:
                    png_bytes = base64.b64decode(b64_buffer)

                    frame_path = os.path.join(video_dir, f"frame_{frame_count:04d}.png")
                    with open(frame_path, "wb") as f:
                        f.write(png_bytes)
                    frame_count += 1

                    if is_gemini_on:
                        print(f"[MEDIA-WS -> GEMINI] Sent image frame. [{frame_path}]")

    except WebSocketDisconnect:
        print("[MEDIA-WS] Connection closed by Recall.ai client")
    except Exception as e:
        print(f"[MEDIA-WS] Stream exception: {e}")
    finally:
        wave_file.close()
        print(f"[MEDIA-WS] Successfully closed recording. Audio: {audio_filename}, Video folder: {video_dir}/")

