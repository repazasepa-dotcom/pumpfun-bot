# main.py
import os
import asyncio
import aiohttp
from aiohttp import web
from telegram import Bot

# -----------------------------
# CONFIG / ENV
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")  # "@channelusername" or numeric chat id
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 15))  # seconds between checks
GECKO_URL = os.getenv(
    "GECKO_POOLS_URL",
    "https://api.geckoterminal.com/api/v2/networks/solana/pools"
)
PORT = int(os.getenv("PORT", "8000"))
HOST = "0.0.0.0"

# -----------------------------
# GLOBALS
# -----------------------------
seen_pools = set()
pending_pools = dict()  # pool_id -> pool data
_bot = None
_client_session = None
_monitor_task = None
prev_stats = dict()  # pool_id -> {"txns": int, "market_cap": float}

# -----------------------------
# TELEGRAM POST FUNCTION
# -----------------------------
async def post_to_channel(token, pool_id):
    global _bot
    symbol = token.get("symbol", "Unknown")
    name = token.get("name", "Unknown")
    base_token = token.get("base_token_symbol", "Unknown")
    txns = token.get("txn_count") or token.get("txns") or 0
    market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0

    msg = (
        f"📢 New pool gaining momentum!\n"
        f"Token: {symbol} | {name}\n"
        f"Base Token: {base_token}\n"
        f"Transactions: {txns}\n"
        f"Liquidity/Market Cap: ${market_cap}\n"
        f"Pool ID: {pool_id}"
    )

    print(msg)
    if _bot:
        try:
            await _bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as e:
            print(f"⚠️ Failed to send Telegram message: {e}")

# -----------------------------
# SEND STARTUP TEST MESSAGE
# -----------------------------
async def send_startup_message():
    if _bot and TELEGRAM_CHAT_ID:
        try:
            await _bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text="✅ Bot started successfully and is now monitoring GeckoTerminal!"
            )
        except Exception as e:
            print(f"⚠️ Failed to send startup test message: {e}")

# -----------------------------
# FETCH POOLS
# -----------------------------
async def fetch_pools():
    global _client_session
    if _client_session is None:
        _client_session = aiohttp.ClientSession()
    try:
        async with _client_session.get(GECKO_URL, timeout=20) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", [])
            return []
    except Exception as e:
        print(f"⚠️ Failed to fetch pools: {e}")
        return []

# -----------------------------
# MONITOR LOOP
# -----------------------------
async def monitor_pools():
    global seen_pools, pending_pools, prev_stats
    print("✅ Bot monitor started and watching GeckoTerminal")
    while True:
        pools = await fetch_pools()

        for pool in pools:
            token = pool.get("attributes", {})
            pool_id = pool.get("id")
            if not pool_id:
                continue

            txns = token.get("txn_count") or token.get("txns") or 0
            market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0

            # Only post if thresholds met
            if txns >= 1 and market_cap >= 5000:
                # Check if pool is new or gaining momentum
                prev = prev_stats.get(pool_id, {"txns": 0, "market_cap": 0})
                if pool_id not in seen_pools or txns > prev["txns"] or market_cap > prev["market_cap"]:
                    await post_to_channel(token, pool_id)
                    seen_pools.add(pool_id)

            # Save stats for next check
            prev_stats[pool_id] = {"txns": txns, "market_cap": market_cap}

        await asyncio.sleep(POLL_INTERVAL)

# -----------------------------
# AIOHTTP WEB APP
# -----------------------------
async def handle_health(request):
    return web.Response(text="OK")

async def handle_metrics(request):
    return web.json_response({
        "seen_pools_count": len(seen_pools),
        "pending_pools_count": len(pending_pools)
    })

async def create_app():
    global _bot, _monitor_task, _client_session
    if TELEGRAM_BOT_TOKEN:
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)

    _client_session = aiohttp.ClientSession()

    asyncio.create_task(send_startup_message())

    loop = asyncio.get_event_loop()
    _monitor_task = loop.create_task(monitor_pools())

    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    return app

# -----------------------------
# MAIN ENTRY
# -----------------------------
if __name__ == "__main__":
    app = asyncio.run(create_app())
    web.run_app(app, host=HOST, port=PORT)
