from struct import pack
import re
import base64
from typing import Dict, List, Tuple, Optional
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import *
from utils import get_settings, save_group_settings, clean_filename
from collections import defaultdict
from datetime import datetime, timedelta
from logging_helper import LOGGER
import time

# --- Database Initialization ---
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

client2 = AsyncIOMotorClient(DATABASE_URI2)
db2 = client2[DATABASE_NAME]
instance2 = Instance.from_db(db2)

# --- Media Document Models ---

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

@instance2.register
class Media2(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

# --- NEW: Series Document Model for Grouping ---

@instance.register
class Series(Document):
    """Stores a group of media files (e.g., all episodes of a season) under one series name."""
    series_name = fields.StrField(required=True, unique=True) # e.g., "Loki S01"
    # List of Media file_id (which is Media._id) that belong to this series
    file_ids = fields.ListField(fields.StrField, required=True) 
    created_at = fields.DateTimeField(default=datetime.utcnow)
    class Meta:
        indexes = ('$series_name', )
        collection_name = 'series'
        
# --- Database Size Caching ---

_db_size_cache = {
    'time': 0,
    'size': 0
}
DB_SIZE_CACHE_DURATION = 60 

async def check_db_size(silentdb):
    try:
        global _db_size_cache
        current_time = time.time()
        is_primary = False
        if isinstance(silentdb, AsyncIOMotorClient) or isinstance(silentdb, type(db)):
            if silentdb.name == db.name: is_primary = True
        elif hasattr(silentdb, 'db'):
            if silentdb.db.name == db.name: is_primary = True
        if is_primary and (current_time - _db_size_cache['time'] < DB_SIZE_CACHE_DURATION):
            return _db_size_cache['size']
        size = 0
        if isinstance(silentdb, AsyncIOMotorClient) or isinstance(silentdb, type(db)):
            size = (await silentdb.command("dbstats"))['dataSize']
        elif hasattr(silentdb, 'db'):
            size = (await silentdb.db.command("dbstats"))['dataSize']
        elif hasattr(silentdb, 'collection'):
            size = (await silentdb.collection.database.command("dbstats"))['dataSize']
        if is_primary:
            _db_size_cache['time'] = current_time
            _db_size_cache['size'] = size
        return size
    except Exception as e:
        LOGGER.error(f"Error checking DB size: {e}")
        return 0
    
# --- Media File Operations (Existing) ---

async def save_file(media) -> Tuple[bool, int]:
    try:
        file_id, file_ref = unpack_new_file_id(media.file_id)
        file_name = clean_filename(media.file_name)
        use_secondary = False
        saveMedia = Media        
        if MULTIPLE_DB:
            primary_db_size = await check_db_size(db)
            db_change_limit_bytes = DB_CHANGE_LIMIT * 1024 * 1024
            if primary_db_size >= db_change_limit_bytes:
                saveMedia = Media2
                use_secondary = True              
        if use_secondary:
            exists_in_primary = await Media.count_documents({'file_id': file_id}, limit=1)
            if exists_in_primary:
                LOGGER.info(f'{file_name} Is Already Saved In Primary Database!')
                return False, 0
        file = saveMedia(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
        await file.commit()
        LOGGER.info(f'{file_name} Saved Successfully In {"Secondary" if use_secondary else "Primary"} Database')
        return True, 1
    except ValidationError as e:
        LOGGER.error(f'Validation Error While Saving File: {e}')
        return False, 2
    except DuplicateKeyError:
        LOGGER.info(f'{file_name} Is Already Saved In {"Secondary" if use_secondary else "Primary"} Database')
        return False, 0
    except Exception as e:
        LOGGER.error(f"Unexpected error in save_file: {e}")
        return False, 3
            

async def get_search_results(chat_id, query, file_type=None, max_results=10, offset=0, filter=None) -> Tuple[List, int, int]:
    if chat_id is not None:
        settings = await get_settings(int(chat_id))
        try:
            user_max_btn = settings.get('max_btn')
            if user_max_btn:
                max_results = 10
            else:
                max_results = int(MAX_B_TN)
        except (KeyError, ValueError):
            await save_group_settings(int(chat_id), 'max_btn', False)
            max_results = int(MAX_B_TN)

    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        parts = query.split(' ')
        new_parts = []
        for part in parts:
            new_parts.append(r"(\b|[\.\+\-_])" + part + r"(\b|[\.\+\-_])")
        raw_pattern = r".*[\s\.\+\-_()\[\]]".join(new_parts)
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except Exception as e:
        LOGGER.error(f"Regex Error: {e}")
        return [], 0, 0
    if not isinstance(filter, dict):
        if USE_CAPTION_FILTER:
            filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
        else:
            filter = {'file_name': regex}
    if file_type:
        filter['file_type'] = file_type
    if max_results % 2 != 0:
        max_results += 1
    
    # Check if the query is a Series Name first
    series_files, series_total = await get_series_files(query)
    if series_files:
        # If a series is found, return its contents
        # We handle pagination manually since we have the full list
        files = series_files[offset:offset + max_results]
        next_offset = offset + len(files)
        if next_offset >= series_total or len(files) == 0:
            next_offset = 0
        return files, next_offset, series_total

    # Proceed with normal media search if no series match
    cursor1 = Media.find(filter).sort('$natural', -1).skip(offset).limit(max_results)
    files = await cursor1.to_list(length=max_results)
    total_results = 0
    if not MULTIPLE_DB:
        if offset == 0 and len(files) < max_results:
            total_results = len(files)
        else:
            total_results = await Media.count_documents(filter)
    else:
        count_db1 = await Media.count_documents(filter)
        count_db2 = await Media2.count_documents(filter)
        total_results = count_db1 + count_db2
        if len(files) < max_results:
            remaining_needed = max_results - len(files)
            if len(files) > 0:
                cursor2 = Media2.find(filter).sort('$natural', -1).limit(remaining_needed)
                files2 = await cursor2.to_list(length=remaining_needed)
                files.extend(files2)
            else:
                if offset >= count_db1:
                    offset_db2 = offset - count_db1
                    cursor2 = Media2.find(filter).sort('$natural', -1).skip(offset_db2).limit(max_results)
                    files = await cursor2.to_list(length=max_results)
                else:
                    pass
    next_offset = offset + len(files)
    if next_offset >= total_results or len(files) == 0:
        next_offset = 0
    return files, next_offset, total_results
    
async def get_bad_files(query, file_type=None):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        parts = query.split(' ')
        new_parts = []
        for part in parts:
            new_parts.append(r"(\b|[\.\+\-_])" + part + r"(\b|[\.\+\-_])")
        raw_pattern = r".*[\s\.\+\-_()]".join(new_parts)
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return [], 0
    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}
    if file_type:
        filter['file_type'] = file_type
    cursor1 = Media.find(filter).sort('$natural', -1)
    files1 = await cursor1.to_list(length=(await Media.count_documents(filter)))
    files = files1
    if MULTIPLE_DB:
        cursor2 = Media2.find(filter).sort('$natural', -1)
        files2 = await cursor2.to_list(length=(await Media2.count_documents(filter)))
        files.extend(files2)
    total_results = len(files)
    return files, total_results
    

async def get_file_details(query):
    filter = {'file_id': query}
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    if not filedetails:
        cursor2 = Media2.find(filter)
        filedetails = await cursor2.to_list(length=1)
    return filedetails


# --- NEW: Series Grouping Functions ---

async def save_series_group(series_name: str, file_ids: List[str]) -> bool:
    """Creates or updates a series group with a list of file IDs."""
    if not series_name or not file_ids:
        LOGGER.error("Series name or file IDs cannot be empty.")
        return False
        
    try:
        # Check if series already exists
        series_doc = await Series.find_one({'series_name': series_name})
        
        if series_doc:
            # Update existing series (e.g., if new episodes are added)
            existing_ids = set(series_doc.file_ids)
            new_ids = set(file_ids)
            
            # Combine and ensure uniqueness
            combined_ids = list(existing_ids.union(new_ids))
            
            series_doc.file_ids = combined_ids
            await series_doc.commit()
            LOGGER.info(f"Series '{series_name}' updated with {len(new_ids - existing_ids)} new files. Total: {len(combined_ids)}")
        else:
            # Create new series
            new_series = Series(
                series_name=series_name,
                file_ids=list(set(file_ids)) # Ensure uniqueness on creation
            )
            await new_series.commit()
            LOGGER.info(f"New series '{series_name}' saved with {len(file_ids)} files.")
        
        return True
        
    except Exception as e:
        LOGGER.error(f"Error saving series group '{series_name}': {e}")
        return False

async def get_series_files(series_name: str) -> Tuple[List[Media], int]:
    """Retrieves all media files belonging to a specific series name."""
    series_doc = await Series.find_one({'series_name': series_name})
    
    if not series_doc:
        return [], 0
        
    file_ids = series_doc.file_ids
    
    # Query all media files using the extracted file_ids
    media_files = []
    
    # We need to query both Media and Media2 collections
    q_filter = {'_id': {'$in': file_ids}}
    
    # Query primary database
    cursor1 = Media.find(q_filter)
    media_files.extend(await cursor1.to_list(length=len(file_ids)))
    
    # Query secondary database if MULTIPLE_DB is enabled
    if MULTIPLE_DB:
        cursor2 = Media2.find(q_filter)
        media_files.extend(await cursor2.to_list(length=len(file_ids)))
        
    # Sort files based on their original order (optional, but good practice for series)
    file_id_to_media = {file.file_id: file for file in media_files}
    ordered_files = [file_id_to_media[fid] for fid in file_ids if fid in file_id_to_media]
    
    return ordered_files, len(ordered_files)
    
async def delete_series_group(series_name: str) -> bool:
    """Deletes the series group entry."""
    try:
        result = await Series.delete_many({'series_name': series_name})
        if result.deleted_count > 0:
            LOGGER.info(f"Series group '{series_name}' deleted.")
            return True
        else:
            LOGGER.info(f"Series group '{series_name}' not found.")
            return False
    except Exception as e:
        LOGGER.error(f"Error deleting series group '{series_name}': {e}")
        return False

# --- File ID Encoding/Decoding (Existing) ---

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
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
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
