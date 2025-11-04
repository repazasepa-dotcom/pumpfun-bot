#!/usr/bin/env python3
import os
import asyncio
import requests
from datetime import datetime
from flask import Flask
from telethon import TelegramClient

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")  # e.g., @yourchannelusername
PORT = int(os.getenv("PORT", 10000))

# -----------------------------
# FLASK KEEP-ALIVE SERVER
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ PumpFun Bot Running & Alive!"

def keep_alive():
    print(f"🌍 Keep-alive running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)

# -----------------------------
# TELEGRAM BOT
# -----------------------------
client = TelegramClient("pumpfun_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Track seen pools to detect new or updated activity
seen = {}

GECKO_URL = "https://www.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10  # seconds between polls

# -----------------------------
# SEND ALERT
# -----------------------------
async def send_alert(symbol, name, txns, mcap, pool_id):
    text = (
        f"🚨 **ALERT: Potential Gem Detected!**\n\n"
        f"💎 Token: {symbol} ({name})\n"
        f"📈 Txns: {txns}\n"
        f"💰 MCAP: ${mcap}\n"
        f"📊 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
    )
    try:
        await client.send_message(CHANNEL, text)
        print(f"✅ Alert sent for {symbol} ({pool_id})")
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

# -----------------------------
# TEST ALERT (verifies channel works)
# -----------------------------
async def test_alert():
    await send_alert("TestCoin", "TEST", 1, 5000, "test_pool")
    print("✅ Test alert sent!")

# -----------------------------
# MONITOR COINS
# -----------------------------
async def monitor():
    print("🚀 Solana Gem Hunter Bot Running...")
    while True:
        print(f"[{datetime.now()}] 🔍 Checking pools... seen={len(seen)}")
        try:
            r = requests.get(GECKO_URL, timeout=10)
            pools = r.json().get("data", [])
        except Exception as e:
            print(f"[{datetime.now()}] ⚠️ Gecko fetch error: {e}")
            await asyncio.sleep(POLL_DELAY)
            continue

        for pool in pools:
            attrs = pool.get("attributes", {})
            token_name = attrs.get("base_token_name", "Unknown")
            token_symbol = attrs.get("base_token_symbol", "Unknown")
            pool_id = pool.get("id", "Unknown")

            txns = int(attrs.get("txn_count", 0) or 0)
            mcap = attrs.get("market_cap_usd", 0) or 0
            try:
                mcap = float(mcap)
            except:
                mcap = 0

            # first appearance
            if pool_id not in seen:
                seen[pool_id] = txns
                if txns >= 1 and mcap >= 5000:
                    await send_alert(token_symbol, token_name, txns, mcap, pool_id)
                continue

            # spike detection
            prev_tx = seen[pool_id]
            if txns > prev_tx + 3:
                await send_alert(token_symbol, token_name, txns, mcap, pool_id)

            seen[pool_id] = txns

        await asyncio.sleep(POLL_DELAY)

# -----------------------------
# MAIN
# -----------------------------
async def main():
    # Send a test alert at startup
    await test_alert()
    # Start monitoring coins
    await monitor()

if __name__ == "__main__":
    # Start keep-alive server in separate thread
    import threading
    threading.Thread(target=keep_alive).start()

    # Run bot loop
    client.loop.run_until_complete(main())
