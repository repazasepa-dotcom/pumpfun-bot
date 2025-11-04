#!/usr/bin/env python3
import os
import asyncio
import aiohttp
from aiohttp import web
from telegram import Bot

# -----------------------------
# CONFIG / ENV
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHANNEL")  # numeric ID or "@channelusername"
GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))
PORT = int(os.getenv("PORT", 10000))
HOST = "0.0.0.0"

# -----------------------------
# GLOBALS
# -----------------------------
seen_pools = {}  # pool_id -> {"txns": int, "mcap": float, "liquidity": float}
_bot = None
_client_session = None

# -----------------------------
# TELEGRAM POST FUNCTION
# -----------------------------
async def post_to_channel(token, pool_id, reason="Potential Pump"):
    symbol = token.get("symbol", "Unknown")
    name = token.get("name", "Unknown")
    base_token = token.get("base_token_symbol", "Unknown")
    txns = int(token.get("txn_count") or token.get("txns") or 0)
    mcap = float(token.get("market_cap_usd") or token.get("liquidity_usd") or 0)

    msg = (
        f"🚨 **MEME COIN ALERT!** 🚨\n\n"
        f"Token: {symbol} | {name}\n"
        f"Base Token: {base_token}\n"
        f"Transactions: {txns}\n"
        f"Market Cap: ${round(mcap,2)}\n"
        f"Pool ID: {pool_id}\n"
        f"Reason: {reason}\n"
        f"Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
    )

    try:
        await _bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Alert sent for {symbol} ({pool_id})")
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

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
            print(f"⚠️ GeckoTerminal API returned status {resp.status}")
            return []
    except Exception as e:
        print(f"⚠️ Error fetching pools: {e}")
        return []

# -----------------------------
# MONITOR LOOP (MEME PUMP DETECTION)
# -----------------------------
async def monitor_pools():
    global seen_pools
    print("🚀 Monitoring Solana pools for potential meme coin pumps...")

    while True:
        pools = await fetch_pools()

        for pool in pools:
            token = pool.get("attributes", {})
            pool_id = pool.get("id")
            if not pool_id:
                continue

            try:
                txns = int(token.get("txn_count") or token.get("txns") or 0)
                mcap = float(token.get("market_cap_usd") or token.get("liquidity_usd") or 0)
                liquidity = float(token.get("liquidity_usd") or 0)
            except (ValueError, TypeError):
                continue

            prev = seen_pools.get(pool_id)
            if not prev:
                seen_pools[pool_id] = {"txns": txns, "mcap": mcap, "liquidity": liquidity}
                continue

            prev_txns = int(prev["txns"])
            prev_mcap = float(prev["mcap"])
            prev_liquidity = float(prev["liquidity"])

            reason = None

            # MEME PUMP DETECTION LOGIC
            if (txns - prev_txns >= 5) and (mcap - prev_mcap >= 5000):
                reason = "High txn spike + Market Cap surge"
            elif (liquidity - prev_liquidity >= 10000):
                reason = "Liquidity surge detected"
            elif (txns >= 10 and mcap < 20000):
                reason = "Low cap high txn activity (classic meme pump)"

            if reason:
                await post_to_channel(token, pool_id, reason)

            # update seen_pools
            seen_pools[pool_id] = {"txns": txns, "mcap": mcap, "liquidity": liquidity}

        await asyncio.sleep(POLL_INTERVAL)

# -----------------------------
# AIOHTTP KEEP-ALIVE
# -----------------------------
async def handle_health(request):
    return web.Response(text="OK")

async def start_app():
    global _bot
    if TELEGRAM_BOT_TOKEN:
        _bot = Bot(token=TELEGRAM_BOT_TOKEN)
        # Startup message
        try:
            await _bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Meme Pump Bot started & monitoring GeckoTerminal!")
        except Exception as e:
            print(f"⚠️ Failed startup message: {e}")

    asyncio.create_task(monitor_pools())

    app = web.Application()
    app.router.add_get("/", handle_health)
    return app

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    web.run_app(start_app(), host=HOST, port=PORT)
