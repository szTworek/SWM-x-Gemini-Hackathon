import json
import os
from datetime import datetime

DB_FILE = "meetings_db.json"

def get_all_meetings() -> dict:
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_meetings(meetings: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(meetings, f, indent=4, ensure_ascii=False)


def create_meeting_if_not_exists(meet_id: str) -> bool:
    meetings = get_all_meetings()

    if meet_id in meetings:
        return False

    meetings[meet_id] = {
        "id": meet_id,
        "created_at": datetime.now().isoformat(),
        "active_bot": False,
        "config": {}  # <-- Dodajemy pusty słownik na konfigurację
    }

    save_meetings(meetings)
    return True


def get_meeting(meet_id: str) -> dict | None:
    meetings = get_all_meetings()
    return meetings.get(meet_id)


def set_bot_active(meet_id: str, is_active: bool, bot_id: str = None):
    meetings = get_all_meetings()
    if meet_id in meetings:
        meetings[meet_id]["active_bot"] = is_active

        if is_active and bot_id:
            meetings[meet_id]["bot_id"] = bot_id
        elif not is_active and "bot_id" in meetings[meet_id]:
            del meetings[meet_id]["bot_id"]

        save_meetings(meetings)

def update_meeting_config(meet_id: str, new_config: dict) -> bool:
    meetings = get_all_meetings()
    if meet_id not in meetings:
        return False

    if "config" not in meetings[meet_id]:
        meetings[meet_id]["config"] = {}

    meetings[meet_id]["config"].update(new_config)
    save_meetings(meetings)
    return True


def get_meetings_with_active_bots() -> list:
    meetings = get_all_meetings()
    active_meetings = []

    for meet_id, data in meetings.items():
        if data.get("active_bot") is True:
            active_meetings.append(data)

    return active_meetings


def get_active_bot_meet_ids() -> list:
    meetings = get_all_meetings()
    res = [(meet_id, data.get('bot_id')) for meet_id, data in meetings.items() if data.get("active_bot") is True]
    return res