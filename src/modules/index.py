import asyncio
import time
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID
from src.database.utils import save_file, temp, get_readable_time
from src import app

lock = asyncio.Lock()
temp.CANCEL = False

@app.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    _, ident, chat, lst_msg_id, skip = query.data.split("#")
    msg = query.message

    if ident == 'yes':
        await msg.edit("<b>📦 Indexing Started!</b>\n\nCollecting files from channel...")
        try:
            chat = int(chat)
        except:
            pass
        await index_files_to_db(int(lst_msg_id), chat, msg, bot, int(skip))
    elif ident == 'cancel':
        temp.CANCEL = True
        await msg.edit("🛑 Cancelling indexing process...")

@app.on_message(filters.command('index') & filters.private & filters.user(OWNER_ID))
async def send_for_index(bot, message):
    if lock.locked():
        return await message.reply('⚠️ Please wait until current process completes.')

    prompt = await message.reply("📩 Forward the last message from channel or send message link")
    msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await prompt.delete()

    if msg.text and msg.text.startswith("https://t.me"):
        try:
            msg_link = msg.text.split("/")
            last_msg_id = int(msg_link[-1])
            chat_id = msg_link[-2]
            chat_id = int("-100" + chat_id) if chat_id.isnumeric() else chat_id
        except:
            return await message.reply('❌ Invalid link format!')
    elif msg.forward_from_chat and msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = msg.forward_from_message_id
        chat_id = msg.forward_from_chat.username or msg.forward_from_chat.id
    else:
        return await message.reply('❌ Invalid message! Must be forwarded channel message or link.')

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f'❌ Error: {e}')

    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply("❌ I can only index channels!")

    s = await message.reply("✏️ Enter number of messages to skip from start:")
    msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await s.delete()

    try:
        skip = int(msg.text)
    except:
        return await message.reply("❌ Invalid number!")

    buttons = [
        [InlineKeyboardButton("✅ START", callback_data=f'index#yes#{chat.id}#{last_msg_id}#{skip}')],
        [InlineKeyboardButton("❌ CANCEL", callback_data=f'index#cancel#{chat.id}#{last_msg_id}#{skip}')]
    ]

    await message.reply(
        f'<b>📚 Indexing Confirmation</b>\n\n'
        f'📌 Channel: {chat.title}\n'
        f'📝 Total Messages: <code>{last_msg_id}</code>\n'
        f'⏩ Skip First: <code>{skip}</code>\n'
        f'📂 To Index: <code>{last_msg_id - skip if last_msg_id > skip else 0}</code>',
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def index_files_to_db(lst_msg_id, chat, msg, bot, skip):
    start_time = time.time()
    stats = {
        'processed': 0,
        'total_files': 0,
        'duplicate': 0,
        'errors': 0,
        'deleted': 0,
        'no_media': 0,
        'unsupported': 0
    }

    async with lock:
        try:
            current_msg_id = lst_msg_id - skip

            if current_msg_id <= 0:
                await msg.edit("⚠️ No messages to index after skipping!")
                return

            while current_msg_id > 0:
                if temp.CANCEL:
                    temp.CANCEL = False
                    duration = get_readable_time(time.time() - start_time)
                    await msg.edit(
                        f"🛑 <b>Indexing Cancelled!</b>\n\n"
                        f"⚙️ Indexing Progress\n\n"
                        f"🔢 Processed: <code>{stats['processed']}</code>\n"
                        f"✅ Saved: <code>{stats['total_files']}</code>\n"
                        f"♻️ Duplicates: <code>{stats['duplicate']}</code>\n"
                        f"🗑️ Deleted: <code>{stats['deleted']}</code>\n"
                        f"🚫 Skipped (No Media): <code>{stats['no_media']}</code>\n"
                        f"❌ Unsupported: <code>{stats['unsupported']}</code>\n"
                        f"⚠️ Errors: <code>{stats['errors']}</code>\n\n"
                        f"⏳ Duration: <code>{duration}</code>"
                    )
                    return

                batch_size = min(200, current_msg_id)
                batch_start = max(1, current_msg_id - batch_size + 1)

                try:
                    messages = await bot.get_messages(
                        chat_id=chat,
                        message_ids=list(range(batch_start, current_msg_id + 1))
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    continue
                except Exception as e:
                    stats['errors'] += batch_size
                    current_msg_id -= batch_size
                    stats['processed'] += batch_size
                    continue

                tasks = []
                for message in messages:
                    stats['processed'] += 1

                    if not message or message.empty:
                        stats['deleted'] += 1
                        continue

                    if not message.media:
                        stats['no_media'] += 1
                        continue

                    if message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT]:
                        stats['unsupported'] += 1
                        continue

                    media = getattr(message, message.media.value, None)
                    if not media or media.mime_type not in ['video/mp4', 'video/x-matroska']:
                        stats['unsupported'] += 1
                        continue

                    media.caption = message.caption
                    tasks.append(save_file(media))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if result == 'suc':
                        stats['total_files'] += 1
                    elif result == 'dup':
                        stats['duplicate'] += 1
                    elif isinstance(result, Exception):
                        stats['errors'] += 1

                progress_msg = (
                    f"⚙️ <b>Indexing Progress</b>\n\n"
                    f"🔢 Processed: <code>{stats['processed']}</code>\n"
                    f"✅ Saved: <code>{stats['total_files']}</code>\n"
                    f"♻️ Duplicates: <code>{stats['duplicate']}</code>\n"
                    f"🗑️ Deleted: <code>{stats['deleted']}</code>\n"
                    f"🚫 Skipped (No Media): <code>{stats['no_media']}</code>\n"
                    f"❌ Unsupported: <code>{stats['unsupported']}</code>\n"
                    f"⚠️ Errors: <code>{stats['errors']}</code>"
                )

                await msg.edit(
                    progress_msg,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🚫 Cancel", callback_data=f"index#cancel#{chat}#{lst_msg_id}#{skip}")
                    ]])
                )

                current_msg_id -= batch_size
                await asyncio.sleep(1)
        except Exception as e:
            await msg.reply(f'❌ Indexing failed: {str(e)}')
        else:
            duration = get_readable_time(time.time() - start_time)
            await msg.edit(
                f"🎉 <b>Indexing Completed!</b>\n\n"
                f"⚙️ Indexing Progress\n\n"
                f"🔢 Processed: <code>{stats['processed']}</code>\n"
                f"✅ Saved: <code>{stats['total_files']}</code>\n"
                f"♻️ Duplicates: <code>{stats['duplicate']}</code>\n"
                f"🗑️ Deleted: <code>{stats['deleted']}</code>\n"
                f"🚫 Skipped (No Media): <code>{stats['no_media']}</code>\n"
                f"❌ Unsupported: <code>{stats['unsupported']}</code>\n"
                f"⚠️ Errors: <code>{stats['errors']}</code>\n\n"
                f"⏳ Duration: <code>{duration}</code>"
            )