# main.py
import os
import asyncio
import aiohttp
from aiohttp import web
from telegram import Bot

# -----------------------------
# CONFIG
# -----------------------------
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", "10000"))
GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools"
POLL_DELAY = 10  # seconds

bot = Bot(TOKEN)
seen_activity = {}  # pool_id -> last tx count seen

# -----------------------------
# Send Telegram Message
# -----------------------------
async def alert(pool, txns, mcap):
    symbol = pool.get("base_token_symbol", "Unknown")
    name = pool.get("base_token_name", "Unknown")
    pool_id = pool.get("id")

    text = (
        f"🚨 **Pump Alert Detected!**\n\n"
        f"Token: {symbol} | {name}\n"
        f"Txns spike: {txns}\n"
        f"Market Cap: ${mcap}\n"
        f"Pool: {pool_id}\n"
        f"Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
    )

    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        print(f"✅ Alert sent for {symbol} ({pool_id})")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# -----------------------------
# Monitor pools
# -----------------------------
async def monitor():
    session = aiohttp.ClientSession()
    print("✅ Bot started — Watching all SOL tokens")

    while True:
        try:
            async with session.get(GECKO_URL, timeout=15) as r:
                data = await r.json()
                pools = data.get("data", [])
        except Exception as e:
            print("⚠️ Error fetching Gecko:", e)
            await asyncio.sleep(POLL_DELAY)
            continue

        for p in pools:
            attrs = p.get("attributes", {})
            pool_id = p.get("id")

            txns = attrs.get("txn_count") or attrs.get("txns") or 0
            mcap = attrs.get("market_cap_usd") or attrs.get("fdv_usd") or attrs.get("liquidity_usd") or 0

            # first sight of pool, store tx count
            if pool_id not in seen_activity:
                seen_activity[pool_id] = txns
                continue

            # check for spike
            prev = seen_activity[pool_id]
            if txns > prev and txns >= 1 and mcap >= 0:
                await alert(attrs, txns, round(mcap, 2))

            seen_activity[pool_id] = txns

        await asyncio.sleep(POLL_DELAY)

# -----------------------------
# Web endpoints (Render keep-alive)
# -----------------------------
async def health(request):
    return web.Response(text="OK")

async def start_app():
    asyncio.create_task(monitor())
    app = web.Application()
    app.router.add_get("/", health)
    return app

if __name__ == "__main__":
    web.run_app(start_app(), host="0.0.0.0", port=PORT)
