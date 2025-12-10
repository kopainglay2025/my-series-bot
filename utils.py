# utils.py (обновленный: добавил русский паттерн в parse_file_name, исключил 'сезон'/'серия' в auto_detect_series)
import logging
from typing import Dict
import re
import os
import requests

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

def fetch_tmdb_ru_title(series_title: str, season: int, episode: int) -> str:
    """
    Пробует получить русское название эпизода из TMDB по названию сериала.
    Возвращает None, если не удалось (не мешает основному потоку).
    """
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return None
    try:
        # 1) ищем сериал
        resp = requests.get(
            "https://api.themoviedb.org/3/search/tv",
            params={"api_key": api_key, "language": "ru-RU", "query": series_title},
            timeout=5,
        )
        data = resp.json()
        if not data.get("results"):
            return None
        tv_id = data["results"][0]["id"]

        # 2) получаем эпизод
        resp = requests.get(
            f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season}/episode/{episode}",
            params={"api_key": api_key, "language": "ru-RU"},
            timeout=5,
        )
        ep_data = resp.json()
        title = ep_data.get("name")
        if title:
            return title.strip()
    except Exception as e:
        logger.warning(f"TMDB fetch failed: {e}")
    return None

# Улучшенный парсер имени файла с поддержкой русских/смешанных названий
def parse_file_name(file_name: str) -> Dict:
    # Telegram заменяет пробелы на подчёркивания — вернём их
    name = file_name.replace("_", " ")

    # Список мусорных тегов для вырезания из title
    trash_tags = r"(1080p|720p|web.?dl|hdrip|bdrip|amzn|nf|kivi|dual|sub|vo|rus|eng|aac|x264|h264)"

    patterns = [
        # S01E02 Название / S01E02.Название / S01E02-Название
        r"(?i)s(?P<season>\d{1,2})[ ._-]*e(?P<episode>\d{1,2})[ ._-]*(?P<title>[^\\/]+)?",
        # E01S01 (инверсия) и e01s01
        r"(?i)e(?P<episode>\d{1,2})[ ._-]*s(?P<season>\d{1,2})[ ._-]*(?P<title>[^\\/]+)?",
        # 1x02 Название
        r"(?i)(?P<season>\d{1,2})x(?P<episode>\d{1,2})[ ._-]*(?P<title>[^\\/]+)?",
        # Сезон 1 серия 02 — Название (ведущие нули, любые тире/точки/пробелы)
        r"(?i)сезон\s*(?P<season>\d{1,2})[ ._-]*сер(ия|и[яи])?\s*(?P<episode>\d{1,2})[ ._-]*[-—–:]?[ ._-]*(?P<title>.+)?",
        # 1 серия Название
        r"(?i)(?P<episode>\d{1,2})\s*сер(ия|и[яи])?\s*[-—–:]?[ ._-]*(?P<title>.+)?",
        # эпизод 3 Название
        r"(?i)эпизод\s*(?P<episode>\d{1,2})[ ._-]*[-—–:]?[ ._-]*(?P<title>.+)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, name)
        if not match:
            continue

        gd = match.groupdict()
        season = int(gd.get("season") or 1)
        episode = int(gd.get("episode") or 1)
        raw_title = gd.get("title") or ""

        # Очищаем хвост: расширение, технические теги, лишние точки/дефисы
        raw_title = re.sub(r"\.(mkv|mp4|avi|mov)$", "", raw_title, flags=re.I)
        raw_title = raw_title.replace(".", " ").replace("-", " ").strip()
        raw_title = re.sub(rf"\s+{trash_tags}.*", "", raw_title, flags=re.I).strip()
        title = raw_title or None

        return {"season": season, "episode": episode, "title": title}

    return {}