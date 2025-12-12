from typing import Callable
from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message
from src import app  

def is_admins(func: Callable) -> Callable:
    async def wrapper(client: Client, message: Message):
        user_id = message.from_user.id
        chat_id = message.chat.id

        chat_member = await client.get_chat_member(chat_id, user_id)
        if chat_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return await func(client, message)

        await message.reply_text("❖ Only admins can access this feature.")

    return wrapper