from pyrogram import filters
from src import app
from datetime import datetime

@app.on_message(filters.command("ping"))
async def ping_pong(client, message):
    await message.reply_text(
        f"<b>🏓 Pong!</b> {await app.ping()} ms"
    )