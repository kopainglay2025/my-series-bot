import asyncio
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from src.database.utils import (
    get_search_results,
    get_size,
    is_admins,
    formate_file_name,
    is_autofilter_enabled,
    enable_autofilter,
    disable_autofilter
)
from config import GROUP_LINK
from src import app

BUTTONS = {}

@app.on_message(filters.command("autofilter") & filters.group & ~filters.bot)
@is_admins
async def chatbot_toggle(_, message: Message):
    chat_id = message.chat.id
    args = message.command[1:]

    if not args:  
        return await message.reply_text("<b>❖ Usage:</b> <code>/autofilter on</code> or <code>/autofilter off</code>")  

    if args[0].lower() in ["on", "enable"]:  
        if await is_autofilter_enabled(chat_id):  
            return await message.reply_text("<b>❖ Auto-filter is already enabled.</b>")  
        await enable_autofilter(chat_id)  
        return await message.reply_text(f"<b>❖ Auto-filter enabled by {message.from_user.mention}.</b>")  

    elif args[0].lower() in ["off", "disable"]:  
        if not await is_autofilter_enabled(chat_id):  
            return await message.reply_text("<b>❖ Auto-filter is already disabled.</b>")  
        await disable_autofilter(chat_id)  
        return await message.reply_text(f"<b>❖ Auto-filter disabled by {message.from_user.mention}.</b>")  

    return await message.reply_text("<b>❖ Invalid option. Use</b> <code>/autofilter on</code> <b>or</b> <code>/autofilter off</code>")

@app.on_message(filters.text & filters.group & ~filters.regex("^/"), group=3)
@app.on_message(filters.command("search") & filters.group)
async def search_files(client, message):
    chat_id = message.chat.id
    query = message.text.strip()
    is_cmd = bool(message.text.startswith("/search"))

    if is_cmd:  
        if len(message.command) == 1:  
            return await message.reply_text("<b>What are you looking for? Type a movie name. 🎥🔍</b>")  
        else:  
            query = " ".join(message.command[1:])

    if not is_cmd and not await is_autofilter_enabled(chat_id):  
        return  

    key = f"{chat_id}-{message.id}"  
    BUTTONS[key] = query    

    searching_msg = await message.reply_text(f"<b>🔍 Searching for</b> <i>{query}</i>...")  

    files, n_offset, total = await get_search_results(query, offset=0)  

    await searching_msg.delete()  

    if not files:  
        return await message.reply_text(f"<b>❖ No results found for</b> <i>{query}</i>.")  

    await send_results(message, files, query, key, n_offset, start_index=1, user_id=message.from_user.id)

async def send_results(message, files, query, key, n_offset, start_index=1, user_id=None):
    me = await app.get_me()
    text = f"<b>🔍 Results for:</b> <i>{query}</i>\n\n"
    for index, file in enumerate(files, start=start_index):
        text += f"<b>{index}. {formate_file_name(file.file_name)}</b>\n"
        text += f"   <b>📦 Size:</b> <code>{get_size(file.file_size)}</code>\n"
        text += f"   <b>🔗 Download:</b> <a href='https://t.me/{me.username}?start=file_{file.file_id}'>Click Here</a>\n\n"

    buttons = []  
    if start_index > 1:  
        buttons.append(InlineKeyboardButton(text="⪻ Back", callback_data=f"back_{key}_{start_index-11}_{user_id}"))  
    if n_offset:  
        buttons.append(InlineKeyboardButton(text="Next ⪼", callback_data=f"next_{key}_{n_offset}_{user_id}"))  

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None  

    await message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)

@app.on_callback_query(filters.regex(r"^(next|back)_"))
async def handle_pagination(bot, query: CallbackQuery):
    data_parts = query.data.split("_")
    if len(data_parts) != 4:
        return await query.answer("Invalid query", show_alert=True)
        
    action, key, offset, user_id = data_parts

    if int(user_id) != query.from_user.id:  
        return await query.answer("⚠ This action is not allowed.", show_alert=True)  

    if key not in BUTTONS:  
        return await query.answer("⚠ Old query expired. Please search again.", show_alert=True)  

    search = BUTTONS.get(key)  
    new_offset = int(offset)  

    if action == "back":  
        new_offset = max(new_offset - 10, 0)  

    files, n_offset, total = await get_search_results(search, offset=new_offset)  
    if not files:  
        return await query.answer("⚠ No more results." if action == "next" else "⚠ No previous results.", show_alert=True)  

    start_index = new_offset + 1  
    await update_results(query.message, files, search, key, n_offset, start_index, new_offset, user_id)

async def update_results(message, files, query, key, n_offset, start_index, offset, user_id):
    me = await app.get_me()
    text = f"<b>🔍 Results for:</b> <i>{query}</i>\n\n"
    for index, file in enumerate(files, start=start_index):
        text += f"<b>{index}. {formate_file_name(file.file_name)}</b>\n"
        text += f"   <b>📦 Size:</b> <code>{get_size(file.file_size)}</code>\n"
        text += f"   <b>🔗 Download:</b> <a href='https://t.me/{me.username}?start=file_{file.file_id}'>Click Here</a>\n\n"

    buttons = []  
    if offset > 0:  
        buttons.append(InlineKeyboardButton(text="⪻ Back", callback_data=f"back_{key}_{offset-10}_{user_id}"))  
    if n_offset:  
        buttons.append(InlineKeyboardButton(text="Next ⪼", callback_data=f"next_{key}_{n_offset}_{user_id}"))  

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None  

    try:  
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)  
    except MessageNotModified:  
        pass
