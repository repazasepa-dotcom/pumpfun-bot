#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from flask import Flask
from telethon import TelegramClient

# -----------------------------
# ENV VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")  # @channelusername or numeric ID
PORT = int(os.getenv("PORT", "10000"))

# GeckoTerminal API URL
GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools"

# -----------------------------
# TELEGRAM CLIENT
# -----------------------------
client = TelegramClient("sol_gem_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# -----------------------------
# KEEP-ALIVE WEB SERVER
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Solana Gem Hunter Bot Running & Alive!"

def keep_alive():
    app.run(host="0.0.0.0", port=PORT)

# -----------------------------
# GLOBALS
# -----------------------------
seen = {}  # pool_id -> {"txns": last_txns, "mcap": last_mcap}
POLL_DELAY = 10  # seconds

# -----------------------------
# SEND TELEGRAM ALERT
# -----------------------------
async def send_alert(text):
    try:
        await client.send_message(CHANNEL, text, parse_mode="Markdown")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# -----------------------------
# NEW POOL ALERT
# -----------------------------
async def new_pool_alert(attrs):
    name = attrs.get("base_token_name", "Unknown")
    symbol = attrs.get("base_token_symbol", "Unknown")
    pool_id = attrs.get("id")
    txns = attrs.get("txn_count") or attrs.get("txns") or 0
    mcap = attrs.get("market_cap_usd") or attrs.get("liquidity_usd") or 0

    text = (
        f"🆕 **NEW SOL GEM FOUND**\n\n"
        f"💎 Token: {symbol} ({name})\n"
        f"📈 Txns: {txns}\n"
        f"💰 Market Cap: ${round(mcap,2)}\n"
        f"📊 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
    )
    await send_alert(text)
    print(f"✅ New pool alert sent: {symbol}")

# -----------------------------
# PUMP ALERT
# -----------------------------
async def pump_alert(attrs, prev_txns, prev_mcap):
    name = attrs.get("base_token_name", "Unknown")
    symbol = attrs.get("base_token_symbol", "Unknown")
    pool_id = attrs.get("id")
    txns = attrs.get("txn_count") or attrs.get("txns") or 0
    mcap = attrs.get("market_cap_usd") or attrs.get("liquidity_usd") or 0

    text = (
        f"🚨 **PUMP ALERT**\n\n"
        f"💎 Token: {symbol} ({name})\n"
        f"📈 Txns: {txns} (+{txns - prev_txns})\n"
        f"💰 Market Cap: ${round(mcap,2)} (+${round(mcap - prev_mcap,2)})\n"
        f"📊 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
    )
    await send_alert(text)
    print(f"🚀 Pump alert sent: {symbol}")

# -----------------------------
# MONITOR POOLS
# -----------------------------
async def monitor_pools():
    async with aiohttp.ClientSession() as session:
        print("🚀 Bot started — monitoring Solana pools")
        while True:
            try:
                async with session.get(GECKO_URL, timeout=15) as resp:
                    data = await resp.json()
                    pools = data.get("data", [])
            except Exception as e:
                print(f"⚠️ Error fetching GeckoTerminal: {e}")
                await asyncio.sleep(POLL_DELAY)
                continue

            for pool in pools:
                attrs = pool.get("attributes", {})
                pool_id = pool.get("id")
                if not pool_id:
                    continue

                txns = attrs.get("txn_count") or attrs.get("txns") or 0
                mcap = attrs.get("market_cap_usd") or attrs.get("liquidity_usd") or 0

                if pool_id not in seen:
                    if txns >= 1 and mcap >= 5000:
                        await new_pool_alert(attrs)
                    seen[pool_id] = {"txns": txns, "mcap": mcap}
                    continue

                # check for pump
                prev = seen[pool_id]
                if (txns - prev["txns"] >= 3) or (mcap - prev["mcap"] >= 5000):
                    await pump_alert(attrs, prev["txns"], prev["mcap"])

                # update last seen
                seen[pool_id] = {"txns": txns, "mcap": mcap}

            await asyncio.sleep(POLL_DELAY)

# -----------------------------
# MAIN ENTRY
# -----------------------------
def run_bot():
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_pools())
    client.run_until_disconnected()

if __name__ == "__main__":
    import threading
    threading.Thread(target=keep_alive).start()
    run_bot()
