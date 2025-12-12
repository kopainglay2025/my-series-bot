import os
import logging
from datetime import datetime
from pyrogram import Client, emoji
from pyrogram.errors import UserNotParticipant, QueryIdInvalid
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InputTextMessageContent,
)
from src.database.utils import get_size, get_search_results
from config import CACHE_TIME, AUTH_CHANNEL, GROUP_LINK
from src import app

FILE_CAPTION = (
    "<b>📁 File Name:</b> {file_name}\n"
    "<b>📦 Size:</b> {size}"
)

@app.on_inline_query()
async def answer(bot, query):
    user_id = query.from_user.id
    query_text = query.query.strip()
    offset = int(query.offset or 0)

    # Force Subscription Check
    try:
        await bot.get_chat_member(AUTH_CHANNEL, user_id)
        is_subscribed = True
    except UserNotParticipant:
        is_subscribed = False

    if not is_subscribed:
        channel = await bot.get_chat(AUTH_CHANNEL)
        join_button = InlineKeyboardButton("ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ", url=channel.invite_link)
        keyboard = InlineKeyboardMarkup([[join_button]])

        await query.answer(
            results=[
                InlineQueryResultArticle(
                    title="Join Channel First",
                    input_message_content=InputTextMessageContent(
                        "🙌 Hey, You're Almost There.\n\n💡 Unlock the magic by joining our channel! Don't miss out on the fun and learning 🎉"
                    ),
                    description="Click to join the channel.",
                    reply_markup=keyboard,
                )
            ],
            is_personal=True,
            cache_time=0
        )
        return

    # If no query text (only @BotUsername), show prompt
    if not query_text:
        return await query.answer(
            results=[
                InlineQueryResultArticle(
                    title="❗️No Query",
                    input_message_content=InputTextMessageContent(
                        "Please enter a movie to search."
                    ),
                    description="🔎 Please enter a movie to search.",
                    reply_markup=get_reply_markup(""),
                )
            ],
            is_personal=True,
            cache_time=0
        )

    results = []

    try:
        files, next_offset, total = await get_search_results(query_text, max_results=10, offset=offset)
    except Exception:
        return await query.answer(
            results=[],
            is_personal=True,
            cache_time=0,
            switch_pm_text="⚠️ Failed to retrieve files.",
            switch_pm_parameter="error"
        )

    for file in files:
        title = file.file_name or "Unknown"
        size = get_size(file.file_size) or "Unknown"
        f_caption = FILE_CAPTION.format(file_name=title, size=size)[:1000]
        reply_markup = get_reply_markup(query_text)

        try:
            results.append(
                InlineQueryResultCachedDocument(
                    title=title,
                    document_file_id=file.file_id,
                    caption=f_caption,
                    description=f'Size: {size}\nType: {file.file_type}',
                    reply_markup=reply_markup
                )
            )
        except AttributeError:
            results.append(
                InlineQueryResultArticle(
                    title=title,
                    input_message_content=InputTextMessageContent(f_caption),
                    description=f'Size: {size}',
                    reply_markup=reply_markup
                )
            )

    if results:
        switch_pm_text = f"{emoji.FILE_FOLDER} Results - {total}" + (f" for {query_text}" if query_text else "")
        try:
            await query.answer(
                results=results,
                is_personal=True,
                cache_time=CACHE_TIME,
                switch_pm_text=switch_pm_text,
                switch_pm_parameter="start",
                next_offset=str(next_offset) if next_offset else None
            )
        except QueryIdInvalid:
            logging.exception("QueryIdInvalid error occurred.")
        except Exception as e:
            logging.exception(str(e))
    else:
        switch_pm_text = f'{emoji.CROSS_MARK} No Results' + (f' for "{query_text}"' if query_text else "")
        await query.answer(
            results=[],
            is_personal=True,
            cache_time=CACHE_TIME,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="okay"
        )


def get_reply_markup(query):
    query = query
    buttons = [[InlineKeyboardButton('⟳ Search Again', switch_inline_query_current_chat=query)]]
    return InlineKeyboardMarkup(buttons)