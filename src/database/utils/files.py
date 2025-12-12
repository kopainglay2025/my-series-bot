import re
import base64
from struct import pack
from pymongo.errors import DuplicateKeyError
from umongo import Document, fields
from marshmallow.exceptions import ValidationError
from pyrogram.file_id import FileId
from src.database import db, instance
from config import COLLECTION_NAME

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id', required=True)
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name',)
        collection_name = COLLECTION_NAME


async def get_files_db_size():
    try:
        stats = await db.command("dbstats")
        return stats['dataSize']
    except Exception:
        return 0


async def save_file(media):
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))

    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
            file_type=media.mime_type.split('/')[0] if media.mime_type else None
        )
        await file.commit()
        return 'suc'

    except ValidationError:
        return 'err'

    except DuplicateKeyError:
        return 'dup'

    except Exception:
        return 'err'


async def search_files(query, max_results=8, offset=0, lang=None):  
    query = query.strip()  
    raw_pattern = (
        r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
        if ' ' not in query else
        query.replace(' ', r'.*[\s\.\+\-_]')
    )

    try:  
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)  
    except Exception:  
        regex = query  

    filter_criteria = {'file_name': regex}  
    cursor = Media.find(filter_criteria).sort('$natural', -1)  

    if lang:  
        lang_files = [
            file async for file in cursor
            if "file_name" in file and lang in file["file_name"].lower()
        ]
        return (
            lang_files[offset:][:max_results],
            offset + max_results if offset + max_results < len(lang_files) else '',
            len(lang_files)
        )

    files = await cursor.skip(offset).limit(max_results).to_list(length=max_results)  
    total_results = await Media.count_documents(filter_criteria)  
    next_offset = offset + max_results if offset + max_results < total_results else ''  

    return files, next_offset, total_results


async def get_bad_files(query, file_type=None):
    query = query.strip()
    raw_pattern = (
        r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
        if ' ' not in query else
        query.replace(' ', r'.*[\s\.\+\-_]')
    )

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except Exception:
        return []

    filter_criteria = {'file_name': regex}
    if file_type:
        filter_criteria['file_type'] = file_type

    files = await Media.find(filter_criteria).sort('$natural', -1).to_list(length=None)
    return files, len(files)


async def get_file_details(file_id):
    try:
        return await Media.find({'file_id': file_id}).to_list(length=1)
    except Exception:
        return []


def encode_file_id(s: bytes) -> str:
    r, n = b"", 0
    for i in s + bytes([22, 4]):
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
    try:
        decoded = FileId.decode(new_file_id)
        return (
            encode_file_id(pack("<iiqq", int(decoded.file_type), decoded.dc_id, decoded.media_id, decoded.access_hash)),
            encode_file_ref(decoded.file_reference)
        )
    except Exception:
        return None, None


def formate_file_name(file_name):
    return ' '.join(
        filter(
            lambda x: not x.startswith('[') and not x.startswith('@') and not x.startswith('www.'),
            file_name.split()
        )
    )