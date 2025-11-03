import os, requests, asyncio
from telethon import TelegramClient
from aiohttp import web

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")
PORT = int(os.getenv("PORT", "10000"))

GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10

seen = {}

client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ---------------------------
# Telegram send function
# ---------------------------
async def send_msg(text):
    try:
        await client.send_message(CHANNEL, text)
        print("✅ Alert sent")
    except Exception as e:
        print("❌ Telegram Error:", e)

# ---------------------------
# Fetch GeckoTerminal
# ---------------------------
def fetch_pools():
    r = requests.get(GECKO_URL, timeout=10)
    return r.json().get("data", [])

# ---------------------------
# Monitor
# ---------------------------
async def monitor():
    print("✅ Solana Gem Hunter Bot Running...")

    while True:
        try:
            pools = fetch_pools()
        except Exception as e:
            print("⚠️ Gecko error:", e)
            await asyncio.sleep(POLL_DELAY)
            continue

        for pool in pools:
            attrs = pool.get("attributes", {})
            token = attrs.get("base_token_name")
            symbol = attrs.get("base_token_symbol")
            pool_id = pool.get("id")

            tx = attrs.get("txn_count", 0)
            mcap = attrs.get("market_cap_usd", 0) or attrs.get("fdv_usd", 0)

            # first detection
            if pool_id not in seen:
                seen[pool_id] = tx
                
                # NEW token alert
                if tx <= 5 and mcap <= 50000:
                    await send_msg(
                        f"🆕 **NEW SOL TOKEN FOUND**\n\n"
                        f"💎 Token: {symbol} ({token})\n"
                        f"💰 Market Cap: ${round(mcap,2)}\n"
                        f"📈 Initial Txns: {tx}\n"
                        f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                    print("🚀 New token alert")
                continue

            prev_tx = seen[pool_id]

            # Volume spike alert
            if tx > prev_tx + 3:
                await send_msg(
                    f"🚨 **Volume Spike Detected!**\n\n"
                    f"💎 Token: {symbol} ({token})\n"
                    f"📈 Txns: {tx} (+{tx-prev_tx})\n"
                    f"💰 MCAP: ${round(mcap,2)}\n"
                    f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                )
                print("📈 Spike alert")

            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

# ---------------------------
# Health Endpoint for Render
# ---------------------------
async def handle(request):
    return web.Response(text="OK ✅ bot running")

async def start_app():
    asyncio.create_task(monitor())
    app = web.Application()
    app.router.add_get("/", handle)
    return app

# ---------------------------
# Run web server
# ---------------------------
if __name__ == "__main__":
    web.run_app(start_app(), port=PORT)
