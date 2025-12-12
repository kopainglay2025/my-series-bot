from src import app
from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest, Message
from pyrogram.errors import HideRequesterMissing

# Event handler for chat join requests
@app.on_chat_join_request(filters.group | filters.channel)
async def autoapprove(client: Client, message: ChatJoinRequest):
    try:
        chat = message.chat
        user = message.from_user
        await client.approve_chat_join_request(chat_id=chat.id, user_id=user.id)

        await client.send_message(
            chat_id=chat.id, 
            text=f"Welcome {user.mention}, to {chat.title}, where every chat feels like a blockbuster. 🎬"
        )
    except HideRequesterMissing:
        # Request was already handled or no longer exists
        pass
    except Exception as e:
        # Log other exceptions
        print(f"Error in autoapprove: {e}")

# Function to delete join messages
@app.on_message(filters.new_chat_members)
async def delete_join_message(client: Client, message: Message):
    try:
        await message.delete()
    except Exception as e:
        print(f"Error deleting join message: {e}")

# Function to delete other service messages
@app.on_message(filters.service & ~filters.new_chat_members)
async def delete_service_messages(client: Client, message: Message):
    try:
        await message.delete()
    except Exception as e:
        print(f"Error deleting service message: {e}")