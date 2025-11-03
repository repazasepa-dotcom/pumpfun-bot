import os, time, requests, asyncio, threading
from datetime import datetime
from telethon import TelegramClient
from flask import Flask

# --------------------------
# Env variables
# --------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")  # Channel @username or chat ID

GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10

seen = {}

# --------------------------
# Telegram Client
# --------------------------
client = TelegramClient("bot", API_ID, API_HASH)

# --------------------------
# Keep Alive Web Server (Render Requires Open Port)
# --------------------------
app = Flask(__name__)

@app.get("/")
def home():
    return "✅ Solana Gem Bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()
    print("🌍 Keep-alive server started")

# --------------------------
# Utils
# --------------------------
async def send_msg(text):
    try:
        await client.send_message(CHANNEL, text)
        print("✅ Alert sent")
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")

def fetch_pools():
    r = requests.get(GECKO_URL, timeout=10)
    return r.json().get("data", [])

# --------------------------
# Bot Monitor
# --------------------------
async def monitor():
    print("✅ Solana Gem Hunter Bot Running...")

    while True:
        print(f"[{datetime.now()}] 🔍 Checking pools... tracked={len(seen)}")

        try:
            pools = fetch_pools()
        except Exception as e:
            print(f"⚠️ Gecko API error: {e}")
            await asyncio.sleep(POLL_DELAY)
            continue

        for p in pools:
            attrs = p.get("attributes", {})
            token = attrs.get("base_token_name")
            symbol = attrs.get("base_token_symbol")
            pool_id = p.get("id")

            tx = int(attrs.get("txn_count", 0) or 0)

            vol = attrs.get("volume_usd", 0)
            if isinstance(vol, dict):
                vol = vol.get("h24", 0)
            vol = float(vol or 0)

            # First time seen
            if pool_id not in seen:
                seen[pool_id] = tx
                print(f"🆕 New token seen: {symbol} | tx={tx} vol={vol}")

                if tx >= 1 and vol >= 5000:
                    print(f"✅ Gem match: {symbol}")
                    await send_msg(
                        f"🆕 **NEW SOL GEM FOUND**\n\n"
                        f"💎 Token: {symbol} ({token})\n"
                        f"💰 Volume: ${round(vol,2)}\n"
                        f"📈 Txns: {tx}\n"
                        f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                continue

            # Spike Alert
            prev_tx = seen[pool_id]
            if tx > prev_tx + 3:
                print(f"🚀 Spike detected: {symbol} {prev_tx}->{tx}")
                await send_msg(
                    f"🚨 **SPIKE ALERT**\n\n"
                    f"💎 Token: {symbol} ({token})\n"
                    f"📈 Txns: {tx} (+{tx-prev_tx})\n"
                    f"💰 Volume: ${round(vol,2)}\n"
                    f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                )

            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

# --------------------------
# Run Bot
# --------------------------
async def start_bot():
    await client.start(bot_token=BOT_TOKEN)
    print("🤖 Telegram bot logged in!")

    # Start monitor loop
    await monitor()

keep_alive()

loop = asyncio.get_event_loop()
loop.run_until_complete(start_bot())
