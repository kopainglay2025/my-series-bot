import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import FILE_AUTO_DEL_TIMER, GROUP_LINK
from src.database.utils import get_size, get_file_details, get_search_results
from src import app
from src.database import add_chat, remove_chat
from src.database.utils import Media, formate_file_name, get_fsub

FILE_DETAILS_CACHE = {}
SEARCH_RESULTS_CACHE = {}

@app.on_message(filters.command("start") & filters.private)
async def start(bot: Client, message: Message) -> None:
    user_id = message.from_user.id

    if not await get_fsub(bot, message):
        return

    data = message.command[1] if len(message.command) > 1 else None
    bot_name = app.name

    if data and data.startswith("file_"):
        parts = data.split("_", 2)
        if len(parts) == 3:
            _, chat_id, file_id = parts
        elif len(parts) == 2:
            _, file_id = parts
        else:
            return await message.reply_text("<b>Invalid file link format.</b>")

        if file_id in FILE_DETAILS_CACHE:
            files_ = FILE_DETAILS_CACHE[file_id]
        else:
            files_ = await get_file_details(file_id)
            if files_:
                FILE_DETAILS_CACHE[file_id] = files_

        if not files_:
            return await message.reply_text("<b>File not found.</b>")

        file = files_[0]
        f_caption = f"📂 <b>{formate_file_name(file.file_name)}</b>\n📦 Size: {get_size(file.file_size)}"

        toDel = await bot.send_cached_media(
            chat_id=message.chat.id,
            file_id=file.file_id,
            caption=f_caption
        )

        msg = await message.reply_text(
            f"<b>Your file will be deleted after {FILE_AUTO_DEL_TIMER / 60:.1f} minutes.</b>",
            reply_to_message_id=toDel.id
        )

        async def delete_after_timeout():
            await asyncio.sleep(FILE_AUTO_DEL_TIMER)
            try:
                await toDel.delete()
                await msg.edit_text("<b>Your file has been deleted.</b>")
            except:
                pass

        asyncio.create_task(delete_after_timeout())
        return

    await message.reply_text(
        f"""
<b>Hey {message.from_user.mention}. 🎬🍿</b>

I am <b>{bot_name}</b>, a movie and TV series provider 🎬 bringing you the latest films, shows, and anime for nonstop entertainment. Want to explore more? Use /help to see all available commands and features. 📜

<i>🎯Monitoring:</i> #Movies #TVSeries #Anime #UnlimitedEntertainment
""",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(text="📢 ᴄʜᴀɴɴᴇʟ", url="https://t.me/CodeSearchDev"),
                InlineKeyboardButton(text="👥 ɢʀᴏᴜᴘs", url="https://t.me/DebugAngels")
            ]
        ]),
        disable_web_page_preview=False,
        reply_to_message_id=message.id
    )

@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    await message.reply_text(
        f"""🎬 <b>Movie Bot Help</b> 🍿

<b>🔍 Search & Download:</b>
• Just type any movie/series name
• Use /imdb <i>movie name</i> for details
• Files auto-delete after {FILE_AUTO_DEL_TIMER // 60} mins

<b>📌 Tips:</b>
• Search with year for better results
• Partial names work (e.g. 'spider')
• Join our group for requests

<i>Enjoy unlimited movies & series!</i>
""",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎥 ᴍᴏᴠɪᴇs ɢʀᴏᴜᴘ", url=GROUP_LINK),
                InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇs", url="https://t.me/CodeSearchDev")
            ],
            [
                InlineKeyboardButton("🔍 ᴛʀʏ ɪɴʟɪɴᴇ sᴇᴀʀᴄʜ", switch_inline_query_current_chat="")
            ]
        ]),
        disable_web_page_preview=True,
        reply_to_message_id=message.id
    )

@app.on_chat_member_updated()
async def chat_updates(client: Client, message: Message) -> None:
    if message.new_chat_member and message.new_chat_member.user.id == app.id:
        asyncio.create_task(add_chat(message.chat.id, message.chat.title))
    elif message.old_chat_member and message.old_chat_member.user.id == app.id and not message.new_chat_member:
        asyncio.create_task(remove_chat(message.chat.id))

async def get_search_results_cached(search, offset=0, max_cache_age=300):
    cache_key = f"{search}_{offset}"
    if cache_key in SEARCH_RESULTS_CACHE:
        timestamp, results = SEARCH_RESULTS_CACHE[cache_key]
        if (asyncio.get_event_loop().time() - timestamp) < max_cache_age:
            return results

    results = await get_search_results(search, offset)
    SEARCH_RESULTS_CACHE[cache_key] = (asyncio.get_event_loop().time(), results)
    return results

@app.on_message(filters.text & filters.private, group=4)
async def auto_filter(client: Client, message: Message) -> None:
    if message.text.startswith("/"):
        return

    search = message.text.strip()
    if not search:
        return

    files, n_offset, total = await get_search_results_cached(search, offset=0)

    if not files:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎥 ᴊᴏɪɴ ᴍᴏᴠɪᴇꜱ ɢʀᴏᴜᴘ", url=GROUP_LINK)]]
        )
        await message.reply_text(
            "🔍 No results found this command works only in group, please join and try there.",
            reply_markup=keyboard,
            reply_to_message_id=message.id
        )