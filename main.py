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

# Render provides PORT env var for web services; default to 8000 locally
PORT = int(os.getenv("PORT", "8000"))
HOST = "0.0.0.0"

# -----------------------------
# GLOBALS
# -----------------------------
seen_pools = set()
_bot = None            # telegram.Bot instance
_client_session = None # aiohttp ClientSession
_monitor_task = None   # asyncio.Task for background monitor

# -----------------------------
# TELEGRAM POST FUNCTION
# -----------------------------
async def post_to_channel(token, pool_id):
    global _bot
    symbol = token.get("symbol", "Unknown")
    name = token.get("name", "Unknown")
    base_token = token.get("base_token_symbol", "Unknown")
    holders = token.get("holders", 0)
    market_cap = token.get("market_cap_usd", 0)
    # Differentiate if no base token but meets criteria
    no_base_badge = ""
    if not token.get("base_token_address") and (holders >= 5 and market_cap >= 5000):
        no_base_badge = "⚠️ No base token but meets holders & market cap criteria\n"

    msg = (
        f"📢 New pool detected!\n"
        f"{no_base_badge}"
        f"Token: {symbol} | {name}\n"
        f"Base Token: {base_token}\n"
        f"Holders: {holders}\n"
        f"Market Cap: ${market_cap}\n"
        f"Pool ID: {pool_id}"
    )
    print(msg)  # local log
    if _bot:
        try:
            # 'send_message' is awaitable in python-telegram-bot v20+
            await _bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as e:
            print(f"⚠️ Failed to send Telegram message: {e}")

# -----------------------------
# FETCH POOLS
# -----------------------------
async def fetch_pools():
    global _client_session
    # Use a single ClientSession for efficiency
    if _client_session is None:
        _client_session = aiohttp.ClientSession()

    try:
        async with _client_session.get(GECKO_URL, timeout=20) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", [])
            else:
                print(f"⚠️ Failed to fetch pools, status: {resp.status}")
                return []
    except Exception as e:
        print(f"⚠️ Exception fetching pools: {e}")
        return []

# -----------------------------
# MONITOR LOOP (background)
# -----------------------------
async def monitor_pools():
    print("✅ Bot monitor started and watching GeckoTerminal")
    global seen_pools
    while True:
        pools = await fetch_pools()
        for pool in pools:
            token = pool.get("attributes", {})
            pool_id = pool.get("id")
            if not pool_id:
                print(f"⚠️ Skipping pool, no ID found: {token.get('symbol', 'Unknown')}")
                continue

            base_token_address = token.get("base_token_address")
            holders = token.get("holders", 0) or 0
            market_cap = token.get("market_cap_usd", 0) or 0

            # Post conditions:
            # - If base_token_address exists -> post
            # - Else if holders >=5 AND market_cap >= 5000 -> post
            should_post = bool(base_token_address) or (holders >= 5 and market_cap >= 5000)

            if should_post and pool_id not in seen_pools:
                await post_to_channel(token, pool_id)
                seen_pools.add(pool_id)
            elif not should_post:
                # helpful debug line
                print(f"⚠️ Skipping pool (does not meet criteria): {token.get('symbol','Unknown')} | holders={holders} market_cap={market_cap}")

        await asyncio.sleep(POLL_INTERVAL)

# -----------------------------
# AIOHTTP WEB APP (health + ping endpoints)
# -----------------------------
async def handle_health(request):
    return web.Response(text="OK")

async def handle_metrics(request):
    return web.json_response({
        "seen_pools_count": len(seen_pools)
    })

async def on_startup(app):
    global _bot, _monitor_task, _client_session
    # Create telegram Bot (async-capable)
    if TELEGRAM_BOT_TOKEN:
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)
    else:
        print("⚠️ BOT_TOKEN not supplied in env; Telegram messages will not be sent.")

    # create a shared aiohttp session as well
    _client_session = aiohttp.ClientSession()
    # start background monitor
    loop = asyncio.get_event_loop()
    _monitor_task = loop.create_task(monitor_pools())
    print("Startup complete. Background monitor task started.")

async def on_cleanup(app):
    global _monitor_task, _client_session, _bot
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    if _client_session:
        await _client_session.close()
    if _bot:
        # Bot doesn't require explicit close; but if using aiohttp session inside it, handle appropriately
        pass
    print("Clean shutdown complete.")

def create_app():
    app = web.Application()
    app.router.add_get("/", handle_health)      # GET / -> returns OK
    app.router.add_get("/metrics", handle_metrics)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

# -----------------------------
# MAIN ENTRY
# -----------------------------
if __name__ == "__main__":
    app = create_app()
    print(f"Starting webserver on {HOST}:{PORT} (Render requires binding to $PORT)")
    web.run_app(app, host=HOST, port=PORT)
