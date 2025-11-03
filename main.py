#!/usr/bin/env python3
import os
import asyncio
import time
import threading
from datetime import datetime
from flask import Flask
from telethon import TelegramClient, events, Button
import requests

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL = os.getenv("CHANNEL", "")  # @channelusername or numeric ID
PORT = int(os.getenv("PORT", 10000))

GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10  # seconds

# -----------------------------
# FLASK KEEP-ALIVE
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ PumpFun Bot Running & Alive!"

def keep_alive():
    print(f"🌍 Keep-alive running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)

# -----------------------------
# TELEGRAM BOT CLIENT
# -----------------------------
client = TelegramClient("pumpfun_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

seen = {}  # pool_id -> last txn count

async def send_msg(text):
    try:
        await client.send_message(CHANNEL, text)
        print(f"✅ Alert sent to channel")
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")

# -----------------------------
# FETCH AND MONITOR POOLS
# -----------------------------
def fetch_pools():
    try:
        resp = requests.get(GECKO_URL, timeout=10)
        data = resp.json().get("data", [])
        return data
    except Exception as e:
        print(f"⚠️ Error fetching GeckoTerminal pools: {e}")
        return []

async def analyze_pools():
    while True:
        pools = fetch_pools()
        print(f"[{datetime.now()}] 🔍 Checking pools... seen={len(seen)}")

        for pool in pools:
            attrs = pool.get("attributes", {})
            pool_id = pool.get("id")
            symbol = attrs.get("base_token_symbol", "Unknown")
            name = attrs.get("base_token_name", "Unknown")

            tx = int(attrs.get("txn_count") or attrs.get("txns") or 0)
            vol = attrs.get("volume_usd") or attrs.get("liquidity_usd") or 0
            if isinstance(vol, dict):
                vol = float(vol.get("h24", 0))
            else:
                vol = float(vol or 0)

            # First-time detection
            if pool_id not in seen:
                seen[pool_id] = tx
                if tx >= 1 and vol >= 5000:
                    print(f"[+] 🆕 GEM FOUND: {symbol} | tx={tx} vol={vol}")
                    await send_msg(
                        f"🆕 **NEW SOL GEM FOUND**\n\n"
                        f"💎 Token: {symbol} ({name})\n"
                        f"💰 24h Volume: ${round(vol,2)}\n"
                        f"📈 Txns: {tx}\n"
                        f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                continue

            # Detect spikes
            prev_tx = seen[pool_id]
            if tx > prev_tx + 3:
                print(f"🚀 Spike detected: {symbol} | tx {prev_tx} -> {tx}")
                await send_msg(
                    f"🚨 **SPIKE ALERT**\n\n"
                    f"💎 Token: {symbol} ({name})\n"
                    f"📈 Txns: {tx} (+{tx-prev_tx})\n"
                    f"💰 24h Volume: ${round(vol,2)}\n"
                    f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                )

            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

# -----------------------------
# /start command
# -----------------------------
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    user = event.sender_id
    print(f"[LOG] /start used by {user}")

    await event.reply(
        "🤖 **PumpFun Solana Bot** is running.\n\n"
        "🔍 Auto-scanning pools\n"
        "📈 Alerts on new tokens and spikes\n\n"
        "✅ Bot online",
        buttons=[
            [Button.url("Join Channel", f"https://t.me/{CHANNEL.strip('@')}")],
            [Button.url("DexScreener", "https://dexscreener.com/")]
        ]
    )

# -----------------------------
# MAIN BOT LOOP
# -----------------------------
def run_bot():
    print("✅ Telegram bot connected")
    print("🚀 Starting Solana pool scan...")
    loop = asyncio.get_event_loop()
    loop.create_task(analyze_pools())
    client.run_until_disconnected()

# -----------------------------
# START
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=keep_alive).start()
    time.sleep(1)
    print("🚀 Starting async bot loop now...")
    run_bot()
