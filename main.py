# main.py
import os, time, json, requests, asyncio
from aiohttp import web
from telethon import TelegramClient

# -------------------- ENV --------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH"))
BOT_TOKEN = os.getenv("BOT_TOKEN"))
CHANNEL = os.getenv("CHANNEL"))  # @channel or ID
PORT = int(os.getenv("PORT", "10000"))

GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools"
POLL = 10

seen = {}
client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# -------------------- SEND MESSAGE --------------------
async def send(text):
    try:
        await client.send_message(CHANNEL, text)
        print("✅ Sent")
    except Exception as e:
        print("❌ Telegram error:", e)

# -------------------- FETCH POOLS --------------------
def fetch():
    try:
        r = requests.get(GECKO_URL, timeout=10)
        return r.json().get("data", [])
    except:
        return []

# -------------------- MONITOR --------------------
async def monitor():
    print("✅ Sol Gem Hunter running...")

    while True:
        pools = fetch()

        for p in pools:
            attr = p.get("attributes", {})
            token = attr.get("base_token_name")
            symbol = attr.get("base_token_symbol")
            pool_id = p.get("id")

            # TX & Volume
            tx = attr.get("txn_count") or 0
            vol = attr.get("volume_usd") or 0
            vol = float(vol) if isinstance(vol, (float, int, str)) else 0

            # First seen = store baseline
            if pool_id not in seen:
                seen[pool_id] = tx

                # 🆕 NEW COIN FOUND
                if tx <= 1 and vol <= 5000:
                    await send(
                        f"🆕 **New SOL Token**\n"
                        f"{symbol} ({token})\n"
                        f"💵 Volume: ${vol}\n"
                        f"🧾 TX: {tx}\n"
                        f"https://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                continue

            prev = seen[pool_id]

            # 📈 PUMP SIGNAL
            if tx > prev and vol >= 5000:
                await send(
                    f"🚨 **Volume Spike**\n"
                    f"{symbol} ({token})\n"
                    f"TX: {tx} (+{tx-prev})\n"
                    f"💵 Volume: ${vol}\n"
                    f"https://www.geckoterminal.com/solana/pools/{pool_id}"
                )

            seen[pool_id] = tx

        await asyncio.sleep(POLL)

# -------------------- WEB (Render keep-alive) --------------------
async def home(request):
    return web.Response(text="Bot alive ✅")

async def run_all():
    asyncio.create_task(monitor())
    app = web.Application()
    app.router.add_get("/", home)
    return app

if __name__ == "__main__":
    web.run_app(run_all(), host="0.0.0.0", port=PORT)
