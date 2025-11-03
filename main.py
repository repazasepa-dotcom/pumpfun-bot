#!/usr/bin/env python3
import os, time, json, requests, threading, asyncio, datetime
from flask import Flask
from telethon import TelegramClient

# -----------------------------
# ENV VARS / SETTINGS
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # use @username for test channel

SOLANA_RPC = os.getenv("SOL_RPC", "https://api.mainnet-beta.solana.com")
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"
CHECK_INTERVAL = 10 if DEBUG_MODE else 120  # 10s for testing, 2min for production

client = TelegramClient("session", API_ID, API_HASH)
holder_history = {}  # {mint: {"first": int, "time": timestamp}}

# -----------------------------
# GET HOLDER COUNT
# -----------------------------
def get_holder_count(mint):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [mint]
    }
    try:
        res = requests.post(SOLANA_RPC, json=payload, timeout=10).json()
        if "result" not in res: return None
        accounts = res["result"]["value"]
        holders = sum(1 for a in accounts if float(a["amount"]) > 0)
        return holders
    except:
        return None

# -----------------------------
# SEND TELEGRAM MESSAGE
# -----------------------------
async def send_telegram(msg):
    try:
        await client.send_message(CHANNEL_ID, msg, link_preview=False)
    except Exception as e:
        print("Telegram Error:", e)

# -----------------------------
# FETCH NEW POOLS FROM GECKOTERMINAL
# -----------------------------
def get_new_pools():
    url = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
    try:
        r = requests.get(url, timeout=10).json()
        return r["data"]
    except:
        return []

# -----------------------------
# ANALYZE TOKEN
# -----------------------------
async def analyze_token(pool):
    try:
        token = pool["attributes"]
        mint = token["base_token_address"]
        name = token["base_token_name"]
        symbol = token["base_token_symbol"]
        volume = float(token.get("volume_usd", 0))

        # Volume filter
        if volume < 50000:
            print(f"⛔ {symbol} low volume: {volume}")
            return

        print(f"\n🎯 New Token: {name} ({symbol}) | Mint: {mint} | Volume: ${volume:,.0f}")

        holders = get_holder_count(mint)
        if holders is None:
            print("⚠️ Could not fetch holders")
            return

        # Initialize first time seen
        if mint not in holder_history:
            holder_history[mint] = {"first": holders, "time": time.time()}
            print(f"🌱 Tracking {symbol} | Initial holders: {holders}")
            return

        # Calculate growth
        initial = holder_history[mint]["first"]
        elapsed = time.time() - holder_history[mint]["time"]
        growth = holders - initial
        growth_per_min = growth / (elapsed / 60) if elapsed > 60 else growth

        print(f"📈 {symbol} Holders: {holders} | +{growth} | {growth_per_min:.2f}/min")

        # Filters
        if holders < 100 or holders > 800:
            print("❌ Holders out of target range")
            return

        if growth < 20 or growth_per_min < 10:
            print("❌ Weak growth — skipping")
            return

        # ✅ Strong coin alert
        msg = f"""
🔥 *Meme Coin Momentum Alert*

*Name:* {name} ({symbol})
*Mint:* `{mint}`

*Volume:* ${volume:,.0f}
*Holders:* {holders}
*Initial:* {initial}
*Growth:* +{growth}
*Speed:* {growth_per_min:.1f}/min

[View Chart](https://www.geckoterminal.com/solana/tokens/{mint})
"""
        await send_telegram(msg)
        print(f"✅ Alert sent for {symbol}")

    except Exception as e:
        print("Analyze Error:", e)

# -----------------------------
# MAIN MONITOR LOOP
# -----------------------------
async def monitor():
    await client.connect()
    if not await client.is_user_authorized():
        await client.start(bot_token=BOT_TOKEN)

    await send_telegram("✅ Bot started and monitoring GeckoTerminal ✅")

    while True:
        print(f"[{datetime.datetime.utcnow().isoformat()}] Checking GeckoTerminal new pools...")
        pools = get_new_pools()
        for p in pools:
            await analyze_token(p)
        await asyncio.sleep(CHECK_INTERVAL)

# -----------------------------
# FLASK KEEP ALIVE
# -----------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Meme bot running"

def run_web():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# -----------------------------
# START
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(monitor())
