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
    # Список общих "мусорных" паттернов для очистки названия эпизода/сериала
    junk_patterns = [
        r'\s*\[.*?\]',  # [1080p], [AnimeRG] и т.д.
        r'\s*\(.*?\)',  # (WEB-DL 1080p, AAC 2.0)
        r'\s*WEB-DL|1080p|720p|4K|HDTV|BluRay|HDR|Dolby|Atmos|AAC|AC3|DTS|x264|x265|h264|h265|HEVC|AVC|MP4|MKV|AVI| subs?|eng|rus|multi|season|episode',  # Тех. теги
        r'\s*\.\w+$',   # .mkv и т.д.
        r'\s*-\s*$',    # Висящие дефисы
    ]
    
    # Паттерны для парсинга (расширенные, с приоритетом на русский формат)
    patterns = [
        # Русский формат как на скрине: "Название. Сезон N Серия M - Эпизод (junk).ext"
        r'(?i)^(.*?)\.?\s*Сезон\s*(\d{1,2})\s*Серия\s*(\d{1,2})\s*-\s*(.*?)\s*(\(.*\))?\.?\w*$',
        # Английский: "Title. Season N Episode M - EpTitle (junk).ext"
        r'(?i)^(.*?)\.?\s*Season\s*(\d{1,2})\s*Episode\s*(\d{1,2})\s*-\s*(.*?)\s*(\(.*\))?\.?\w*$',
        # S05E07 - Title (junk).ext
        r'(?i)^(.*?)\.?\s*S(\d{1,2})E(\d{1,2})\s*-\s*(.*?)(\s*\[.*\]|\s*\(.*\))?\.?\w*$',
        # Title.S05E16.junk.ext
        r'(?i)^(.*?)\.S(\d{1,2})E(\d{1,2})\.?(.*?)(\s*\[.*\]|\s*\(.*\))?\.?\w*$',
        # Title - 1105 [junk].ext (аниме, сезон=1)
        r'(?i)^(.*?)\s*-\s*(\d{3,4})\s*(\[.*\]|\(.*\))?\.?\w*$',  # episode only, season=1
        # [Group] Title - 001 [junk].ext
        r'(?i)^(\[.*\])?\s*(.*?)\s*-\s*(\d{1,3})\s*(\[.*\]|\(.*\))?\.?\w*$',
        # 1x01 - Title.ext
        r'(?i)^(.*?)\.?\s*(\d{1,2})x(\d{1,2})\s*-\s*(.*?)(\s*\[.*\]|\s*\(.*\))?\.?\w*$',
        # Just number: Title.101.junk.ext (season=1, episode=01)
        r'(?i)^(.*?)\.(\d)(\d{2})\.?(.*?)(\s*\[.*\]|\s*\(.*\))?\.?\w*$',
    ]
    
    clean_name = file_name.strip()
    for pattern in patterns:
        match = re.match(pattern, clean_name)
        if match:
            groups = match.groups()
            # Определяем, что где (в зависимости от паттерна)
            if len(groups) >= 5:  # Полный русский/английский с junk
                series_title = groups[0].strip()
                season = int(groups[1])
                episode = int(groups[2])
                ep_title = groups[3].strip() if groups[3] else None
            elif len(groups) == 4:  # SxxExx без series или с junk
                series_title = groups[0].strip() if groups[0] else None
                season = int(groups[1])
                episode = int(groups[2])
                ep_title = groups[3].strip() if groups[3] else None
            elif len(groups) == 3:  # Аниме-style или simple
                series_title = groups[0].strip() if groups[0] else None
                season = 1
                episode = int(groups[1] if groups[1].isdigit() else groups[2])
                ep_title = groups[2].strip() if len(groups) > 2 and groups[2] and not groups[2].startswith('[') else None
            else:
                continue
            
            # Очистка series_title и ep_title от junk
            for junk in junk_patterns:
                series_title = re.sub(junk, '', series_title or '', flags=re.IGNORECASE).strip() if series_title else None
                ep_title = re.sub(junk, '', ep_title or '', flags=re.IGNORECASE).strip() if ep_title else None
            
            # Если ep_title пустое — дефолт
            if not ep_title:
                ep_title = f"Серия {episode}"
            
            return {
                'series_title': series_title,
                'season': season,
                'episode': episode,
                'title': ep_title
            }
    
    # Если ничего не распарсилось — пустой dict
    return {}