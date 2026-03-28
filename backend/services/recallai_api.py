import os
import httpx
from fastapi import HTTPException

RECALL_API_KEY = os.getenv("RECALL_API_KEY", "your_api_key_here")
RECALL_BASE_URL = "https://eu-central-1.recall.ai/api/v1"


async def create_recall_bot(meet_id: str, bot_name: str = "Meeting Assistant"):
    if meet_id.startswith("http"):
        meeting_url = meet_id
    else:
        meeting_url = f"https://meet.google.com/{meet_id}"

    headers = {
        "Authorization": f"Token {RECALL_API_KEY}",
        "Content-Type": "application/json"
    }

    base_url = os.getenv(
        "WEBHOOK_BASE_URL",
        "https://leslee-undemonstrational-crankly.ngrok-free.dev"
    )
    webhook_url = f"{base_url}/meeting/webhook/recall"
    ws_media_url = base_url.replace("https://", "wss://").replace("http://",
                                                                  "ws://") + f"/meeting/ws/recall-media/{meet_id}"

    payload = {
        "meeting_url": meeting_url,
        "bot_name": bot_name,
        "output_media": {
            "camera": {
                "kind": "webpage",
                "config": {
                    "url": f"{base_url}/bot_media/bot_sandbox/{meet_id}"
                }
            }
        },
        "recording_config": {
            "transcript": {
                "provider": {
                    "meeting_captions": {}
                }
            },
            "audio_mixed_raw": {},
            "video_separate_png": {},
            "realtime_endpoints": [
                {
                    "type": "webhook",
                    "url": webhook_url,
                    "events": ["transcript.data", "transcript.partial_data"]
                },
                {
                    "type": "websocket",
                    "url": ws_media_url,
                    "events": ["audio_mixed_raw.data", "video_separate_png.data"]
                }
            ]
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{RECALL_BASE_URL}/bot/",
                json=payload,
                headers=headers,
                timeout=10.0
            )
        except Exception as e:
            print(f"[RecallAI] API connection error: {e}")
            raise HTTPException(status_code=500, detail="Cannot connect to Recall API")

        if response.status_code not in (200, 201):
            print(f"[RecallAI] Error creating bot: {response.text}")
            raise HTTPException(status_code=500, detail=f"Recall API Error: {response.text}")

        return response.json()


async def leave_recall_bot(bot_id: str) -> bool:
    """
    Wysyła sygnał do Recall.ai, aby bot natychmiast opuścił spotkanie.
    """
    headers = {
        "Authorization": f"Token {RECALL_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{RECALL_BASE_URL}/bot/{bot_id}/leave_call/"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, timeout=10.0)
            if response.status_code in (200, 201, 204):
                print(f"[RecallAI] Bot {bot_id} otrzymał polecenie opuszczenia spotkania.")
                return True
            else:
                print(f"[RecallAI] Błąd wycofywania bota {bot_id}: {response.text}")
                return False
        except Exception as e:
            print(f"[RecallAI] Wyjątek podczas wycofywania bota {bot_id}: {e}")
            return False
