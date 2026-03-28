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
        "active_bot": False
    }

    save_meetings(meetings)
    return True


def get_meeting(meet_id: str) -> dict | None:
    meetings = get_all_meetings()
    return meetings.get(meet_id)


def set_bot_active(meet_id: str, is_active: bool):
    meetings = get_all_meetings()
    if meet_id in meetings:
        meetings[meet_id]["active_bot"] = is_active
        save_meetings(meetings)
