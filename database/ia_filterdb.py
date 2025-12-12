import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow import ValidationError
from info import *
from utils import get_settings, save_group_settings
from datetime import datetime, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# ---------------------------------------------------------

# Global cache for DB size
_db_stats_cache = {"timestamp": None, "primary_size": 0.0}

# Primary DB
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

# secondary db
client2 = AsyncIOMotorClient(DATABASE_URI2)
db2 = client2[DATABASE_NAME]
instance2 = Instance.from_db(db2)


# Regex to flexibly extract Series Name, Season (SXX), and Episode (EYY)
# This handles variations like S01E01, S1.EP01, Season 1 Episode 1, etc.
EPISODE_REGEX = re.compile(
    r'(.+?)[.\s\-_]?S(\d+)[.\s\-_]?(?:E|EP|Episode)[.\s\-_]?(\d+)',
    re.IGNORECASE
)

# --- UMONGO Document Definitions ---

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


@instance2.register
class Media2(Document):
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME

# --- Helper Functions for Series Grouping ---

def extract_series_episode(filename: str) -> Optional[Dict[str, str]]:
    """
    Extracts Series Name, Season (SXX), and Episode (EYY) from a filename.
    Returns: {'name': str, 'season': str, 'episode': str, 'id_key': str} or None
    """
    match = EPISODE_REGEX.search(filename)
    if match:
        # Group 1: Series Name, clean up trailing separators
        name = match.group(1).replace('.', ' ').replace('_', ' ').replace('-', ' ').strip()
        
        # Group 2: Season number (pad to 2 digits)
        season = match.group(2).zfill(2)
        
        # Group 3: Episode number (pad to 2 digits)
        episode = match.group(3).zfill(2)
        
        # The unique identifier key for grouping: NAME_SXXEYY
        id_key = f"{name.upper().replace(' ', '_')}_S{season}E{episode}"
        
        return {
            'name': name,
            'season': season,
            'episode': episode,
            'id_key': id_key
        }
    return None


async def group_media_by_episode(files: List[Media]) -> Dict[str, List[Media]]:
    """
    Groups a list of Media documents by their SXXEYY identifier.
    Files with different resolutions (e.g., 720P, 1080P) but the same SXXEYY
    will be in the same list. This fulfills the requirement to show all qualities.
    
    Returns: A dictionary where keys are 'SXX EYY' (e.g., 'S01 E01') 
             and values are a list of Media objects for that episode.
    """
    grouped_results = defaultdict(list)
    for file in files:
        # NOTE: File name attribute is accessed directly on the umongo document
        info = extract_series_episode(file.file_name) 
        if info:
            # Group by SXX EYY for user-friendly display (e.g., 'S01 E01')
            group_key = f"S{info['season']} E{info['episode']}"
            grouped_results[group_key].append(file)
        else:
            # Group files that don't match the series/episode pattern separately
            grouped_results['Other'].append(file)
            
    # Sort the episode keys numerically
    sorted_groups = {}
    
    # Sort keys for SXX EYY (e.g., S01 E01, S01 E02, S02 E01...)
    # The 'SXX EYY' format allows for lexicographical sorting which mostly works for standard series
    episode_keys = sorted([k for k in grouped_results.keys() if k != 'Other'])
    
    for key in episode_keys:
        sorted_groups[key] = grouped_results[key]
        
    if 'Other' in grouped_results and grouped_results['Other']:
        sorted_groups['Other'] = grouped_results['Other']
        
    return sorted_groups

# --- Database Operations ---

async def check_db_size(db):
    try:
        now = datetime.utcnow()
        cache_stale_by_time = _db_stats_cache["timestamp"] is None or (
            now - _db_stats_cache["timestamp"] > timedelta(minutes=10)
        )
        refresh_if_size_threshold = _db_stats_cache["primary_size"] >= 10.0
        if not cache_stale_by_time and not refresh_if_size_threshold:
            return _db_stats_cache["primary_size"]
        stats = await db.command("dbstats")
        db_logical_size = stats["dataSize"]
        db_index_size = stats["indexSize"]
        db_logical_size_mb = db_logical_size / (1024 * 1024)
        db_index_size_mb = db_index_size / (1024 * 1024)
        db_size_mb = db_logical_size_mb + db_index_size_mb
        _db_stats_cache["primary_size"] = db_size_mb
        _db_stats_cache["timestamp"] = now
        return db_size_mb
    except Exception as e:
        print(f"Error Checking Database Size: {e}")
        return 0


async def save_file(media):
    """Save file in database, with detailed logging."""
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(
        r"[_\-\.#+$%^&*()!~`,;:\"'?/<>\[\]{}=|\\]", " ", str(media.file_name)
    )
    file_name = re.sub(r"\s+", " ", file_name).strip()
    saveMedia = Media
    target_db = "Primary"
    if MULTIPLE_DB:
        try:
            # NOTE: count_documents is a method on the collection/model instance provided by motor/umongo
            exists = await Media.count_documents({"file_id": file_id}, limit=1)
            if exists:
                logger.info(f"[SKIP] '{file_name}' already in Primary DB.")
                return False, 0
            primary_db_size = await check_db_size(db)
            if primary_db_size >= 407:
                saveMedia = Media2
                target_db = "Secondary"
                logger.warning("Switching to Secondary DB due to size threshold.")
        except Exception as e:
            logger.error(
                "Error during MULTIPLE_DB check; defaulting to primary DB.", exc_info=e
            )
    try:
        record = saveMedia(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=(media.caption.html if media.caption and INDEX_CAPTION else None),
        )
    except ValidationError as e:
        logger.exception(f"[VALIDATION ERROR] '{file_name}' → {e}")
        return False, 2
    try:
        await record.commit()
    except DuplicateKeyError:
        logger.info(
            f"[SKIP] DuplicateKey: '{file_name}' already exists in {target_db} DB."
        )
        return False, 0
    except Exception as e:
        logger.exception(
            f"[ERROR] Failed commit of '{file_name}' to {target_db} DB.", exc_info=e
        )
        return False, 3
    logger.info(f"[SUCCESS] '{file_name}' saved to {target_db} DB.")
    return True, 1


async def get_search_results(chat_id, query, file_type=None, max_results=None, filter=False, offset=0):
    if chat_id is not None:
        settings = await get_settings(int(chat_id))
        if max_results is None:
            try:
                # Assuming max_btn True means use a default like 10
                max_results = 10 if settings.get("max_btn") else int(MAX_B_TN)
            except KeyError:
                await save_group_settings(int(chat_id), "max_btn", True)
                settings = await get_settings(int(chat_id))
                max_results = 10 if settings.get("max_btn") else int(MAX_B_TN)

    # --- Search Query Construction ---
    if isinstance(query, list):
        # This part handles season searches etc., where you need to match any of the full phrases.
        raw_pattern = '|'.join(re.escape(q.strip()) for q in query if q.strip())
        regex_list = [re.compile(raw_pattern, re.IGNORECASE)] if raw_pattern else []
        
        if USE_CAPTION_FILTER:
            # Using $or with multiple regexes for file_name and caption
            filter_mongo = {"$or": [{"file_name": r} for r in regex_list] + [{"caption": r} for r in regex_list]}
        else:
            filter_mongo = {"$or": [{"file_name": r} for r in regex_list]}
    else:
        query = query.strip()
        if not query:
            return [], None, 0
            
        # This is the key change for balancing speed and flexibility
        if ' ' in query:
            # For multi-word queries, allow spaces, dots, or hyphens between words.
            # Use '.*?' to allow other characters in between
            words = [re.escape(word) for word in query.split()]
            raw_pattern = r'.*'.join(words)
        else:
            # For single-word queries, use word boundaries for accuracy.
            raw_pattern = r"\b" + re.escape(query) + r"\b"

        try:
            # Compile the single, main regex pattern
            regex = re.compile(raw_pattern, flags=re.IGNORECASE)
        except re.error:
            return [], None, 0

        if USE_CAPTION_FILTER:
            filter_mongo = {"$or": [{"file_name": regex}, {"caption": regex}]}
        else:
            filter_mongo = {"file_name": regex}

    if file_type:
        filter_mongo["file_type"] = file_type
    
    # --- Fetching Results ---
    if ULTRA_FAST_MODE:
        limit = max_results + 1
        find_tasks = [Media.find(filter_mongo).sort("$natural", -1).skip(offset).limit(limit).to_list(length=limit)]
        if MULTIPLE_DB:
            find_tasks.append(Media2.find(filter_mongo).sort("$natural", -1).skip(offset).limit(limit).to_list(length=limit))
        
        results = await asyncio.gather(*find_tasks)
        files = results[0]
        if MULTIPLE_DB and len(results) > 1:
            files.extend(results[1])
            
        files = files[:limit]

        has_next_page = len(files) > max_results
        if has_next_page:
            files = files[:-1]

        next_offset = offset + len(files) if has_next_page else ""
        total_results = offset + len(files) + (1 if has_next_page else 0)
    else:
        # Standard mode: Count documents first
        count_tasks = [Media.count_documents(filter_mongo)]
        find_tasks = [Media.find(filter_mongo).sort("$natural", -1).skip(offset).limit(max_results).to_list(length=max_results)]

        if MULTIPLE_DB:
            count_tasks.append(Media2.count_documents(filter_mongo))
            find_tasks.append(Media2.find(filter_mongo).sort("$natural", -1).skip(offset).limit(max_results).to_list(length=max_results))
        
        count_results, find_results = await asyncio.gather(
            asyncio.gather(*count_tasks),
            asyncio.gather(*find_tasks)
        )
        
        total_results = sum(count_results)
        files = find_results[0]
        if MULTIPLE_DB and len(find_results) > 1:
            files.extend(find_results[1])
        
        files = files[:max_results]
        
        next_offset = offset + len(files)
        if next_offset >= total_results:
            next_offset = ""

    return files, next_offset, total_results

async def get_series_episode_groups(chat_id, query, offset=0, file_type=None, max_results=None, filter=False) -> Dict[str, List[Media]]:
    """
    Retrieves all search results matching the query and groups them by episode (SXX EYY).
    
    This function is designed to support the user's request for showing all versions 
    (e.g., 720p, 1080p) of a single episode under one episode key.
    
    Note: offset and max_results are ignored here as we need all results to group correctly.
    """
    
    # 1. Fetch all matching files (no limit/offset)
    # Reusing the search results logic but without pagination limits for full grouping
    files, _, _ = await get_search_results(
        chat_id=chat_id, 
        query=query, 
        file_type=file_type, 
        max_results=200, # Use a reasonable cap to prevent massive queries, but large enough for most seasons
        offset=0, 
        filter=filter
    )
    
    # 2. Group the retrieved files by their episode identifier
    grouped_media = await group_media_by_episode(files)
    
    return grouped_media


async def get_bad_files(query, file_type=None):
    query = query.strip()
    if not query:
        # If query is empty, match any file name (but this should probably be restricted in use)
        raw_pattern = '.' 
    elif ' ' not in query:
        # If single word, match word boundary for accuracy
        raw_pattern = r"\b" + re.escape(query) + r"\b"
    else:
        # If multi-word, match sequentially, allowing separators in between (simple version)
        words = [re.escape(word) for word in query.split()]
        raw_pattern = r'.*'.join(words)
        
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []
        
    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}
        
    if file_type:
        filter['file_type'] = file_type
        
    # Find all documents in both dbs for bad file check
    files1 = await Media.find(filter).sort('$natural', -1).to_list()
    
    if MULTIPLE_DB:
        files2 = await Media2.find(filter).sort('$natural', -1).to_list()
        files = files1 + files2
    else:
        files = files1
        
    total_results = len(files)
    return files, total_results


async def get_file_details(query):
    filter = {"file_id": query}
    
    tasks = [Media.find(filter).to_list(length=1)]
    if MULTIPLE_DB:
        tasks.append(Media2.find(filter).to_list(length=1))
        
    results = await asyncio.gather(*tasks)
    
    for filedetails in results:
        if filedetails:
            return filedetails
            
    return []


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0

            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash,
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref

async def dreamxbotz_fetch_media(limit: int) -> List[dict]:
    try:
        if MULTIPLE_DB:
            db_size = await check_db_size(Media)
            if db_size > 407:
                cursor = Media2.find().sort("$natural", -1).limit(limit)
                files = await cursor.to_list(length=limit)
                return files
        cursor = Media.find().sort("$natural", -1).limit(limit)
        files = await cursor.to_list(length=limit)
        return files
    except Exception as e:
        logger.error(f"Error in dreamxbotz_fetch_media: {e}")
        return []


async def dreamxbotz_clean_title(filename: str, is_series: bool = False) -> str:
    try:
        year_match = re.search(r"^(.*?(\d{4}|\(\d{4}\)))", filename, re.IGNORECASE)
        if year_match:
            title = year_match.group(1).replace("(", "").replace(")", "")
            return (
                re.sub(
                    r"(?:@[^ \n\r\t.,:;!?()\[\]{}<>\\\/\"'=_%]+|[._\-\[\]@()]+)",
                    " ",
                    title,
                )
                .strip()
                .title()
            )
        if is_series:
            season_match = re.search(
                r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))(?:\s*Combined)?",
                filename,
                re.IGNORECASE,
            )
            if season_match:
                title = season_match.group(1).strip()
                season = (
                    season_match.group(2)
                    or season_match.group(3)
                    or season_match.group(4)
                )
                title = (
                    re.sub(
                        r"(?:@[^ \n\r\t.,:;!?()\[\]{}<>\\\/\"'=_%]+|[._\-\[\]@()]+)",
                        " ",
                        title,
                    )
                    .strip()
                    .title()
                )
                return f"{title} S{int(season):02}"
        title = filename
        return (
            re.sub(
                r"(?:@[^ \n\r\t.,:;!?()\[\]{}<>\\\/\"'=_%]+|[._\-\[\]@()]+)", " ", title
            )
            .strip()
            .title()
        )
    except Exception as e:
        logger.error(f"Error in truncate_title: {e}")
        return filename


async def dreamxbotz_get_movies(limit: int = 20) -> List[str]:
    try:
        cursor = await dreamxbotz_fetch_media(limit * 2)
        results = set()
        pattern = r"(?:s\d{1,2}|season\s*\d+|season\d+)(?:\s*combined)?(?:e\d{1,2}|episode\s*\d+)?\b"
        for file in cursor:
            file_name = getattr(file, "file_name", "")
            if not re.search(pattern, file_name, re.IGNORECASE):
                title = await dreamxbotz_clean_title(file_name)
                results.add(title)
            if len(results) >= limit:
                break
        return sorted(list(results))[:limit]
    except Exception as e:
        logger.error(f"Error in dreamxbotz_get_movies: {e}")
        return []


async def dreamxbotz_get_series(limit: int = 30) -> Dict[str, List[int]]:
    try:
        cursor = await dreamxbotz_fetch_media(limit * 5)
        grouped = defaultdict(list)
        pattern = r"(.*?)(?:S(\d{1,2})|Season\s*(\d+)|Season(\d+))(?:\s*Combined)?(?:E(\d{1,2})|Episode\s*(\d+))?\b"
        for file in cursor:
            file_name = getattr(file, "file_name", "")
            match = re.search(pattern, file_name, re.IGNORECASE)
            if match:
                title = await dreamxbotz_clean_title(match.group(1), is_series=True)
                season = int(match.group(2) or match.group(3) or match.group(4))
                grouped[title].append(season)
        return {
            title: sorted(set(seasons))[:10]
            for title, seasons in grouped.items()
            if seasons
        }
    except Exception as e:
        logger.error(f"Error in dreamxbotz_get_series: {e}")
        return []
