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
    Sends a signal to Recall.ai for the bot to immediately leave the meeting.
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
                print(f"[RecallAI] Bot {bot_id} has been told to leave the meeting.")
                return True
            else:
                print(f"[RecallAI] Error withdrawing bot {bot_id}: {response.text}")
                return False
        except Exception as e:
            print(f"[RecallAI] Exception while withdrawing bot {bot_id}: {e}")
            return False


async def send_chat_message(bot_id: str, message: str) -> bool:
    """
    Sends a chat message via the bot to all participants in the meeting.
    Google Meet limit: 500 characters, recipient: 'everyone'.
    """
    headers = {
        "Authorization": f"Token {RECALL_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{RECALL_BASE_URL}/bot/{bot_id}/send_chat_message/"

    # Google Meet has a 500-character limit — trim with a notice if needed
    if len(message) > 490:
        message = message[:487] + "..."

    payload = {
        "to": "everyone",
        "message": message,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            if response.status_code in (200, 201, 204):
                print(f"[RecallAI] Chat message sent via bot {bot_id}: {message[:80]}...")
                return True
            else:
                print(f"[RecallAI] Failed to send chat message: {response.status_code} {response.text}")
                return False
        except Exception as e:
            print(f"[RecallAI] Exception sending chat message: {e}")
            return False


async def get_chat_messages(bot_id: str, limit: int = 20) -> list[dict]:
    """
    Fetches the last `limit` chat messages for a bot session via Recall.ai REST API.
    Returns a list of dicts with keys: sender_name, message, created_at.
    """
    headers = {
        "Authorization": f"Token {RECALL_API_KEY}",
        "Accept": "application/json",
    }
    url = f"{RECALL_BASE_URL}/bot/{bot_id}/chat_messages/"
    params = {"page_size": max(1, min(limit, 100))}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", data) if isinstance(data, dict) else data
                messages = []
                for item in results[-limit:]:
                    sender = item.get("participant", {})
                    messages.append({
                        "sender": sender.get("name", "Unknown"),
                        "message": item.get("text", item.get("message", "")),
                        "created_at": item.get("created_at", ""),
                    })
                return messages
            else:
                print(f"[RecallAI] Failed to get chat messages: {response.status_code} {response.text}")
                return []
        except Exception as e:
            print(f"[RecallAI] Exception getting chat messages: {e}")
            return []
