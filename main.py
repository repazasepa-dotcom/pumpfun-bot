import os, time, requests, asyncio
from telethon import TelegramClient, events
from flask import Flask

# -----------------------------
# ENV VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")  # @channel or channel ID

GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10

seen = {}

# -----------------------------
# TELEGRAM BOT
# -----------------------------
client = TelegramClient("gecko_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def send_msg(text):
    try:
        await client.send_message(CHANNEL, text)
        print("✅ Alert sent")
    except Exception as e:
        print("❌ Telegram Error:", e)

def fetch_pools():
    r = requests.get(GECKO_URL, timeout=10)
    return r.json().get("data", [])

# -----------------------------
# BOT COMMANDS
# -----------------------------
@client.on(events.NewMessage(pattern="/ping"))
async def ping(event):
    await event.reply("✅ Bot is running")

# -----------------------------
# MONITOR POOLS
# -----------------------------
async def monitor():
    print("✅ Solana Gem Hunter Bot Running...")

    while True:
        try:
            pools = fetch_pools()
        except Exception as e:
            print("⚠️ API Error:", e)
            await asyncio.sleep(POLL_DELAY)
            continue

        for pool in pools:
            attr = pool.get("attributes", {})
            token = attr.get("base_token_name")
            symbol = attr.get("base_token_symbol")
            pool_id = pool.get("id")

            # ✅ Fix volume field type (dict/string/float)
            vol_raw = attr.get("volume_usd", 0)
            if isinstance(vol_raw, dict):
                vol = float(vol_raw.get("h24", 0) or 0)
            else:
                vol = float(vol_raw or 0)

            tx = int(attr.get("txn_count", 0) or 0)

            # ✅ First time seen
            if pool_id not in seen:
                seen[pool_id] = tx

                # 🆕 NEW TOKEN FILTER (Tx 0–1 + Volume < $5000)
                if tx <= 1 and vol <= 5000:
                    await send_msg(
                        f"🆕 **NEW SOL TOKEN FOUND**\n\n"
                        f"💎 {symbol} ({token})\n"
                        f"📈 Txns: {tx}\n"
                        f"💰 Volume: ${vol:,.2f}\n"
                        f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                continue

            prev_tx = seen[pool_id]

            # 🚨 VOLUME / TX SPIKE ALERT
            if tx > prev_tx + 3:
                await send_msg(
                    f"🚨 **Volume Spike Detected!**\n\n"
                    f"💎 {symbol} ({token})\n"
                    f"📈 Txns: {tx} (+{tx-prev_tx})\n"
                    f"💰 Volume: ${vol:,.2f}\n"
                    f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                )

            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

# -----------------------------
# KEEP ALIVE FOR RENDER
# -----------------------------
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Solana Gecko Bot Running"

async def start_bot():
    await monitor()

client.loop.create_task(start_bot())

# Start web server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
