import os
import asyncio
from telethon import TelegramClient

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")

client = TelegramClient('test', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def test_post():
    await client.send_message(TELEGRAM_CHAT, "✅ Test message from bot!")

client.loop.run_until_complete(test_post())
