#!/usr/bin/env python3
import asyncio
import json
import os
import random
import threading
import time
from datetime import datetime
from flask import Flask
from telethon import TelegramClient, events, Button

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "")  # your channel ID or @username
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# -----------------------------
# KEEP-ALIVE WEB SERVER (Render)
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ PumpFun Bot Running & Alive!"

def keep_alive():
    port = int(os.getenv("PORT", 10000))
    print(f"🌍 Keep-alive running on port {port}")
    app.run(host="0.0.0.0", port=port)

# -----------------------------
# TELEGRAM BOT CLIENT
# -----------------------------
client = TelegramClient("pumpfun_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# -----------------------------
# BOT LOGIC
# -----------------------------
seen = set()  # Track already notified tokens

async def send_msg(text):
    try:
        await client.send_message(CHANNEL, text)
        print(f"✅ Alert sent: {text.splitlines()[0]}")
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")

async def analyze_pools():
    while True:
        print(f"[{datetime.now()}] 🔍 Checking pools... seen={len(seen)}")

        # Replace this with actual pool fetching from API or webpage
        dummy_token = {
            "name": f"Token{random.randint(1,999)}",
            "mint": f"Mint_{random.randint(1000,9999)}",
            "tx_count": random.randint(0, 15),
            "mcap": random.randint(1000, 20000)  # Use MCAP instead of volume
        }

        pool_id = dummy_token["mint"]
        tx = dummy_token["tx_count"]
        mcap = dummy_token["mcap"]

        print(f"[DEBUG] Checking pool {dummy_token['name']} | tx={tx} | mcap={mcap}")

        # First sight
        if pool_id not in seen:
            seen.add(pool_id)
            print(f"[+] 🆕 Token spotted: {dummy_token['name']} | tx={tx} | mcap={mcap}")

            # Criteria: tx >= 1 and mcap >= 5000
            if tx >= 1 and mcap >= 5000:
                print(f"[ALERT] Matched criteria — sending alert: {dummy_token['name']}")
                await send_msg(
                    f"🆕 **NEW SOL GEM FOUND**\n\n"
                    f"💎 Token: {dummy_token['name']}\n"
                    f"📈 Txns: {tx}\n"
                    f"💰 Market Cap: ${mcap}\n"
                    f"📊 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
                )

        # Example spike detection
        prev_tx = seen.count(pool_id) if pool_id in seen else 0
        if tx > prev_tx + 3:
            print(f"🚀 Spike detected: {dummy_token['name']} | tx {prev_tx} -> {tx}")
            await send_msg(
                f"🚨 **SPIKE ALERT**\n\n"
                f"💎 Token: {dummy_token['name']}\n"
                f"📈 Txns: {tx} (+{tx-prev_tx})\n"
                f"💰 Market Cap: ${mcap}\n"
                f"📊 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
            )

        await asyncio.sleep(10)  # polling delay

# -----------------------------
# TELEGRAM COMMANDS
# -----------------------------
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
    time.sleep(1)  # allow web server to boot
    print("🚀 Starting async bot loop now...")
    run_bot()
