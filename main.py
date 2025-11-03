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
pending_pools = dict()  # pool_id -> pool data for retry
_bot = None
_client_session = None
_monitor_task = None

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
        f"Market Cap: ${market_cap}\n"
        f"Pool ID: {pool_id}"
    )

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
    global seen_pools, pending_pools
    print("✅ Bot monitor started and watching GeckoTerminal")
    while True:
        pools = await fetch_pools()

        # Process new pools
        for pool in pools:
            token = pool.get("attributes", {})
            pool_id = pool.get("id")
            if not pool_id or pool_id in seen_pools:
                continue

            txns = token.get("txn_count") or token.get("txns") or 0
            market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0

            if txns >= 20 and market_cap >= 5000:
                await post_to_channel(token, pool_id)
                seen_pools.add(pool_id)
            else:
                pending_pools[pool_id] = token

        # Retry pending pools
        for pool_id in list(pending_pools.keys()):
            token = pending_pools[pool_id]
            txns = token.get("txn_count") or token.get("txns") or 0
            market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0
            if txns >= 20 and market_cap >= 5000:
                await post_to_channel(token, pool_id)
                seen_pools.add(pool_id)
                del pending_pools[pool_id]

        await asyncio.sleep(POLL_INTERVAL)

# -----------------------------
# AIOHTTP WEB APP
# -----------------------------
async def handle_health(request):
    return web.Response(text="OK")

async def on_startup(app):
    global _bot, _monitor_task, _client_session
    if TELEGRAM_BOT_TOKEN:
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)

    _client_session = aiohttp.ClientSession()

    # Send startup test message
    asyncio.create_task(send_startup_message())

    # Start monitor loop
    loop = asyncio.get_event_loop()
    _monitor_task = loop.create_task(monitor_pools())

async def on_cleanup(app):
    global _monitor_task, _client_session
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    if _client_session:
        await _client_session.close()
    print("Clean shutdown complete.")

def create_app():
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

# -----------------------------
# MAIN ENTRY
# -----------------------------
if __name__ == "__main__":
    app = create_app()
    print(f"Starting webserver on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
