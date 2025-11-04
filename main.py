#!/usr/bin/env python3
import os
import asyncio
import threading
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telethon import TelegramClient, Button, events

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "")  # @channelusername or numeric ID
PORT = int(os.getenv("PORT", "10000"))

# -----------------------------
# GLOBALS
# -----------------------------
seen = {}  # coin_id -> {"txns": last_txn, "mcap": last_mcap}
POLL_DELAY = 10  # seconds
PUMP_FUN_URL = "https://pump.fun/?view=table&coins_sort=created_timestamp"
TXN_SPIKE = 3
MCAP_SPIKE = 10000  # $10k spike threshold
MCAP_GROWTH_PERCENT = 50  # minimum % growth to alert
TXN_GROWTH_MULTIPLIER = 2  # minimum TXN growth factor to alert

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
# TELEGRAM CLIENT
# -----------------------------
client = TelegramClient("pumpfun_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def send_alert(token_name, symbol, txns, mcap, coin_link, alert_type="NEW GEM", growth_txn=None, growth_mcap=None):
    growth_text = ""
    if growth_txn is not None:
        growth_text += f"\n📈 TXN Growth: {growth_txn:+}"
    if growth_mcap is not None:
        growth_text += f"\n💰 MCAP Growth: +${growth_mcap:.2f}"

    text = (
        f"🚨 **{alert_type}!**\n\n"
        f"💎 Token: {symbol} ({token_name})\n"
        f"📈 Transactions: {txns}\n"
        f"💰 Market Cap: ${mcap}{growth_text}\n"
        f"🔗 [View on Pump.Fun]({coin_link})"
    )
    try:
        await client.send_message(CHANNEL, text, parse_mode="Markdown")
        print(f"[{datetime.now()}] ✅ Alert sent for {symbol} ({alert_type})")
    except Exception as e:
        print(f"[{datetime.now()}] ⚠️ Telegram Error: {e}")

# -----------------------------
# SCRAPE PUMP.FUN
# -----------------------------
def fetch_coins():
    try:
        r = requests.get(PUMP_FUN_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        coins = []
        if table:
            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 5:
                    continue
                coin_name = cols[1].text.strip()
                symbol = cols[2].text.strip()
                txns = int(cols[3].text.strip() or 0)
                mcap_text = cols[4].text.strip().replace("$","").replace(",","")
                try:
                    mcap = float(mcap_text)
                except:
                    mcap = 0
                coin_id = f"{coin_name}_{symbol}"
                coins.append({
                    "id": coin_id,
                    "name": coin_name,
                    "symbol": symbol,
                    "txns": txns,
                    "mcap": mcap
                })
        return coins
    except Exception as e:
        print(f"[{datetime.now()}] ⚠️ Error fetching Pump.Fun: {e}")
        return []

# -----------------------------
# MONITOR LOOP
# -----------------------------
async def monitor_loop():
    print(f"[{datetime.now()}] 🔍 PumpFun Bot Started")
    while True:
        coins = fetch_coins()
        for c in coins:
            coin_id = c["id"]
            txns = c["txns"]
            mcap = c["mcap"]
            coin_link = f"https://pump.fun/?coin={coin_id}"

            if coin_id not in seen:
                # First time seeing the coin
                seen[coin_id] = {"txns": txns, "mcap": mcap}
                if txns >= 1 and mcap >= 5000:
                    await send_alert(c["name"], c["symbol"], txns, mcap, coin_link, "NEW GEM")
            else:
                prev = seen[coin_id]
                txn_delta = txns - prev["txns"]
                mcap_delta = mcap - prev["mcap"]

                txn_growth = txn_delta
                mcap_growth_percent = (mcap_delta / prev["mcap"] * 100) if prev["mcap"] > 0 else 0

                # Spike or growth alert
                if txn_delta >= TXN_SPIKE or mcap_delta >= MCAP_SPIKE or txn_growth >= TXN_GROWTH_MULTIPLIER or mcap_growth_percent >= MCAP_GROWTH_PERCENT:
                    await send_alert(
                        c["name"], c["symbol"], txns, mcap, coin_link,
                        alert_type="POTENTIAL PUMP",
                        growth_txn=txn_delta,
                        growth_mcap=mcap_delta
                    )
                    seen[coin_id] = {"txns": txns, "mcap": mcap}

        print(f"[{datetime.now()}] ℹ️ Checked pools, total seen={len(seen)}")
        await asyncio.sleep(POLL_DELAY)

# -----------------------------
# TELEGRAM /start COMMAND
# -----------------------------
@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    user = event.sender_id
    print(f"[{datetime.now()}] /start used by {user}")
    await event.reply(
        "🤖 PumpFun Bot is running!\n"
        "🔍 Monitoring new coins & spikes for potential pumps.\n"
        "✅ Bot online.",
        buttons=[
            [Button.url("Join Channel", "https://t.me/pumpfun")],
            [Button.url("Pump.Fun", "https://pump.fun/")]
        ]
    )

# -----------------------------
# RUN BOT & KEEP-ALIVE
# -----------------------------
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(monitor_loop())
    print(f"[{datetime.now()}] 🤖 Telegram bot starting...")
    client.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=keep_alive).start()
    time.sleep(1)
    print(f"[{datetime.now()}] 🚀 Starting async bot loop now...")
    run_bot()
