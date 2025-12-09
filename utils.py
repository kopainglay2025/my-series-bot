# utils.py (обновленный: улучшил parse_file_name с несколькими паттернами)
import logging
from typing import Dict
import re

logger = logging.getLogger("media_bot")
logger.setLevel(logging.INFO)
handler = logging.FileHandler("bot_errors.log", encoding="utf-8")
fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(fmt)
logger.addHandler(handler)

# In-memory state for simple flows (not persisted). For single-user personal bot this is OK.
pending_actions = {}  # chat_id -> dict with pending flow info
last_bot_message = {}  # chat_id -> message_id (so we can delete previous info message)
last_video_message = {}  # chat_id -> message_id (for deleting previous video/document)

def set_pending(chat_id: int, data: dict, key: str = "default"):
    if chat_id not in pending_actions:
        pending_actions[chat_id] = {}
    pending_actions[chat_id][key] = data

def get_pending(chat_id: int, key: str = "default"):
    return pending_actions.get(chat_id, {}).get(key, {})

def pop_pending(chat_id: int, key: str = "default"):
    if chat_id in pending_actions and key in pending_actions[chat_id]:
        return pending_actions[chat_id].pop(key)
    return {}

def set_last_bot_msg(chat_id: int, message_id: int):
    last_bot_message[chat_id] = message_id

def get_last_bot_msg(chat_id: int):
    return last_bot_message.get(chat_id)

def set_last_video_msg(chat_id: int, message_id: int):
    last_video_message[chat_id] = message_id

def get_last_video_msg(chat_id: int):
    return last_video_message.get(chat_id)

# Улучшенный парсер имени файла с поддержкой нескольких форматов
def parse_file_name(file_name: str) -> Dict:
    patterns = [
        # S05E07 - Title.ext
        r'(?i)S(\d{1,2})E(\d{1,2})\s*-\s*(.*)\.\w+$',
        # Title.S05E16.1080p.mkv
        r'(?i)\.?S(\d{1,2})E(\d{1,2})\.?(.*)\.\w+$',
        # Title - 1105 [1080p].mkv (для аниме, предполагаем сезон=1 или ongoing)
        r'(?i)^.*\s*-\s*(\d{3,4})\s*\[.*\]\.\w+$',  # episode only, season=1
        # [AnimeRG] Title - 001 [res].mkv
        r'(?i)^.*\s*-\s*(\d{1,3})\s*\[.*\]\.\w+$',
        # 1x01 - Title.ext
        r'(?i)(\d{1,2})x(\d{1,2})\s*-\s*(.*)\.\w+$',
        # Season 1 Episode 1 Title.ext
        r'(?i)Season\s*(\d{1,2})\s*Episode\s*(\d{1,2})\s*(.*)\.\w+$',
        # S01E01.Title.ext
        r'(?i)S(\d{1,2})E(\d{1,2})\.?(.*)\.\w+$',
        # 01x01 Title.ext (rare)
        r'(?i)(\d{1,2})x(\d{1,2})\s*(.*)\.\w+$',
        # Just number: Title.101.ext (season=1, episode=01)
        r'(?i)\.?(\d)(\d{2})\.?(.*)\.\w+$',  # как 101 -> S1E01
        # Breaking.Bad.S05E16.1080p.mkv
        r'(?i)\.?S(\d{1,2})E(\d{1,2})\.?(.*)\.\w+$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, file_name)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                season = int(groups[0])
                episode = int(groups[1])
                title = groups[2].strip() if groups[2] else None
            elif len(groups) == 2:  # episode only with title
                season = 1
                episode = int(groups[0])
                title = groups[1].strip() if groups[1] else None
            elif len(groups) == 1:  # episode only
                season = 1
                episode = int(groups[0])
                title = None
            else:
                continue
            return {
                'season': season,
                'episode': episode,
                'title': title
            }
    return {}  # nothing parsed