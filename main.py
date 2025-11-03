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
    holders = token.get("holders") or token.get("holders_count") or 0
    market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0

    no_base_badge = ""
    if not token.get("base_token_address"):
        no_base_badge = "⚠️ No base token\n"

    msg = (
        f"📢 New pool detected!\n"
        f"{no_base_badge}"
        f"Token: {symbol} | {name}\n"
        f"Base Token: {base_token}\n"
        f"Holders: {holders}\n"
        f"Market Cap: ${market_cap}\n"
        f"Pool ID: {pool_id}"
    )
    print(msg)
    if _bot:
        try:
            # Use synchronous send_message to ensure it posts immediately
            _bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as e:
            print(f"⚠️ Failed to send Telegram message: {e}")

# -----------------------------
# SEND STARTUP TEST MESSAGE
# -----------------------------
def send_startup_message():
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                             text="✅ Bot started successfully and is now monitoring GeckoTerminal!")
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
            else:
                print(f"⚠️ Failed to fetch pools, status: {resp.status}")
                return []
    except Exception as e:
        print(f"⚠️ Exception fetching pools: {e}")
        return []

# -----------------------------
# MONITOR LOOP
# -----------------------------
async def monitor_pools():
    global seen_pools, pending_pools
    print("✅ Bot monitor started and watching GeckoTerminal")
    while True:
        print(f"⏱ Checking GeckoTerminal... Seen {len(seen_pools)} pools so far")
        pools = await fetch_pools()

        # Retry pending pools first
        for pool_id in list(pending_pools.keys()):
            token = pending_pools[pool_id]
            holders = token.get("holders") or token.get("holders_count") or 0
            market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0
            if holders >= 1 and market_cap >= 5000:
                await post_to_channel(token, pool_id)
                seen_pools.add(pool_id)
                del pending_pools[pool_id]

        # Process new pools
        for pool in pools:
            token = pool.get("attributes", {})
            pool_id = pool.get("id")
            if not pool_id or pool_id in seen_pools:
                continue

            holders = token.get("holders") or token.get("holders_count") or 0
            market_cap = token.get("market_cap_usd") or token.get("liquidity_usd") or 0
            base_token_address = token.get("base_token_address")

            should_post = bool(base_token_address) or (holders >= 1 and market_cap >= 5000)

            if should_post:
                if holders >= 1 and market_cap >= 5000:
                    await post_to_channel(token, pool_id)
                    seen_pools.add(pool_id)
                else:
                    pending_pools[pool_id] = token
            else:
                print(f"⚠️ Skipping pool: {token.get('symbol','Unknown')} | holders={holders} market_cap={market_cap}")

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

async def on_startup(app):
    global _bot, _monitor_task, _client_session
    if TELEGRAM_BOT_TOKEN:
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)
    else:
        print("⚠️ BOT_TOKEN not supplied; Telegram messages disabled")

    _client_session = aiohttp.ClientSession()

    # send startup test message
    send_startup_message()

    loop = asyncio.get_event_loop()
    _monitor_task = loop.create_task(monitor_pools())
    print("Startup complete. Background monitor task started.")

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
    app.router.add_get("/metrics", handle_metrics)
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
