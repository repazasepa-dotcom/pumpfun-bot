#!/usr/bin/env python3
import asyncio
import json
import os
import random
import threading
import time
from flask import Flask
from telethon import TelegramClient, events, Button

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

app = Flask(__name__)

# -----------------------------
# KEEP-ALIVE WEB SERVER (Render)
# -----------------------------
@app.route("/")
def home():
    return "✅ PumpFun Bot Running & Alive!"

def keep_alive():
    port = int(os.getenv("PORT", 10000))
    print(f"🌍 Keep-alive running on port {port}")
    app.run(host="0.0.0.0", port=port)

# -----------------------------
# BOT CLIENT
# -----------------------------
client = TelegramClient("pumpfun_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

seen = set()  # just for debug

async def analyze_pools():
    while True:
        print(f"[LOG] 🔍 Checking pools... seen={len(seen)}")
        
        # Simulated token data (replace when you add API)
        dummy_token = {
            "name": "TestToken",
            "mint": f"Mint_{random.randint(1000,9999)}",
            "tx_count": random.randint(1, 15),
            "volume": random.randint(3000, 20000)
        }

        if dummy_token["mint"] not in seen:
            seen.add(dummy_token["mint"])
            print(f"[+] 🆕 Token found: {dummy_token['name']} | tx={dummy_token['tx_count']} | vol={dummy_token['volume']}")
        
        await asyncio.sleep(10)  # Polling delay


@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    user = event.sender_id
    print(f"[LOG] /start used by {user}")

    await event.reply(
        "🤖 **PumpFun Solana Bot** is running.\n\n"
        "🔍 Auto-scanning pools\n"
        "📈 Alerts on new tokens\n\n"
        "✅ Bot online",
        buttons=[
            [Button.url("Join Channel", "https://t.me/pumpfun")],
            [Button.url("DexScreener", "https://dexscreener.com/")]
        ]
    )

# -----------------------------
# MAIN
# -----------------------------
def run_bot():
    print("✅ Telegram bot connected")
    print("🚀 Starting Solana pool scan...")
    loop = asyncio.get_event_loop()
    loop.create_task(analyze_pools())
    client.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=keep_alive).start()
    time.sleep(1)  # ✅ Allow web server to boot

    print("🚀 Starting async bot loop now...")
    run_bot()
