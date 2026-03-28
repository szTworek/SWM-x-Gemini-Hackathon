import logging
import os
from typing import Any

import httpx


DOCS_BOT_BASE_URL = os.getenv('DOCS_BOT_BASE_URL', 'http://127.0.0.1:8001').rstrip('/')
DOCS_BOT_TIMEOUT_SECONDS = float(os.getenv('DOCS_BOT_TIMEOUT_SECONDS', '2.0'))
DOCS_BOT_CONNECT_TIMEOUT_SECONDS = float(os.getenv('DOCS_BOT_CONNECT_TIMEOUT_SECONDS', '1.0'))


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        timeout=DOCS_BOT_TIMEOUT_SECONDS,
        connect=DOCS_BOT_CONNECT_TIMEOUT_SECONDS,
    )


async def _post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    url = f"{DOCS_BOT_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.post(url, json=payload or {})
            response.raise_for_status()
            return response.json()
    except Exception as error:
        logging.warning(f"[DOCS-BOT] POST {url} failed: {error}")
        return None


async def _get(path: str) -> dict[str, Any] | None:
    url = f"{DOCS_BOT_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as error:
        logging.warning(f"[DOCS-BOT] GET {url} failed: {error}")
        return None


async def start_meeting_pipeline(meet_id: str, title: str | None = None, chat_webhook_url: str | None = None) -> dict[str, Any] | None:
    return await _post(f"/meeting/{meet_id}/start", {
        'title': title,
        'chatWebhookUrl': chat_webhook_url,
    })


async def forward_recall_transcript(payload: dict[str, Any]) -> dict[str, Any] | None:
    return await _post('/meeting/webhook/recall', payload)


async def end_meeting_pipeline(meet_id: str) -> dict[str, Any] | None:
    return await _post(f'/meeting/{meet_id}/end')


async def get_pipeline_status(meet_id: str) -> dict[str, Any] | None:
    return await _get(f'/meeting/{meet_id}/status')
