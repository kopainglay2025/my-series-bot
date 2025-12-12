from pyrogram import enums
import pytz, re, os
from datetime import datetime
from src.database import chatsdb
from src.database.utils import Media

class temp:
    CURRENT = int(os.environ.get("SKIP", 2))
    CANCEL = False

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def get_name(name):
    return re.sub(r'@\w+', '', name)

def list_to_str(k):    
    return "N/A" if not k else ', '.join(str(item) for item in k)

def get_status():
    tz = pytz.timezone('Asia/Colombo')
    hour = datetime.now(tz).time().hour
    if 5 <= hour < 12:
        return "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ"
    elif 12 <= hour < 18:
        return "ɢᴏᴏᴅ ᴀꜰᴛᴇʀɴᴏᴏɴ"
    else:
        return "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ"

async def is_check_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in {enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER}
    except:
        return False

def get_readable_time(seconds):
    periods = [('days', 86400), ('hour', 3600), ('min', 60), ('sec', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name} '
    return result.strip()

async def get_search_results(query, max_results=8, offset=0, lang=None):
    query = query.strip()
    escaped_query = re.escape(query)
    raw_pattern = r'.*'.join(escaped_query.split())

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(query), flags=re.IGNORECASE)

    query_filter = {'file_name': regex}
    cursor = Media.find(query_filter).sort('$natural', -1)

    if lang:
        lang_files = [file async for file in cursor if lang in file.file_name.lower()]
        return (
            lang_files[offset:offset + max_results],
            offset + max_results if offset + max_results < len(lang_files) else '',
            len(lang_files)
        )

    files = await cursor.skip(offset).limit(max_results).to_list(length=max_results)
    total_results = await Media.count_documents(query_filter)
    next_offset = offset + max_results if offset + max_results < total_results else ''
    return files, next_offset, total_results

async def is_autofilter_enabled(chat_id: int) -> bool:
    return await chatsdb.find_one({"chat_id": chat_id}) is None

async def enable_autofilter(chat_id: int):
    await chatsdb.delete_one({"chat_id": chat_id})

async def disable_autofilter(chat_id: int):
    if not await chatsdb.find_one({"chat_id": chat_id}):
        await chatsdb.insert_one({"chat_id": chat_id})

async def get_enabled_chats() -> list:
    chats = await chatsdb.find({}, {"chat_id": 1, "_id": 0}).to_list(length=None)
    return [chat["chat_id"] for chat in chats]