import asyncio
import aiohttp
import os
from telegram import Bot

# -----------------------------
# CONFIGURATION (Render env variables)
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")  # e.g., "@channelusername" or chat_id
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 15))  # default 15s

# -----------------------------
# SETUP
# -----------------------------
bot = Bot(token=TELEGRAM_BOT_TOKEN)
seen_pools = set()  # Track already seen pool IDs

# -----------------------------
# TELEGRAM POST FUNCTION
# -----------------------------
async def post_to_channel(token, pool_id):
    symbol = token.get("symbol", "Unknown")
    name = token.get("name", "Unknown")
    base_token = token.get("base_token_symbol", "Unknown")
    holders = token.get("holders", 0)
    market_cap = token.get("market_cap_usd", 0)
    msg = (
        f"📢 New pool detected!\n"
        f"Token: {symbol} | {name}\n"
        f"Base Token: {base_token}\n"
        f"Holders: {holders}\n"
        f"Market Cap: ${market_cap}\n"
        f"Pool ID: {pool_id}"
    )
    print(msg)  # log locally
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# -----------------------------
# FETCH POOLS FROM GeckoTerminal
# -----------------------------
async def fetch_pools():
    url = "https://api.geckoterminal.com/api/v2/networks/solana/pools"  # Solana pools
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
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
    print("✅ Bot started and monitoring GeckoTerminal ✅")
    while True:
        pools = await fetch_pools()
        for pool in pools:
            token = pool.get("attributes", {})
            pool_id = pool.get("id")
            if not pool_id:
                print(f"⚠️ Skipping pool, no ID found: {token.get('symbol', 'Unknown')}")
                continue

            # Get pool data
            base_token_address = token.get("base_token_address")
            holders = token.get("holders", 0)
            market_cap = token.get("market_cap_usd", 0)

            # Post conditions:
            # 1. Base token exists OR (holders >=5 and market cap >= 5000)
            should_post = base_token_address or (holders >= 5 and market_cap >= 5000)

            if should_post and pool_id not in seen_pools:
                await post_to_channel(token, pool_id)
                seen_pools.add(pool_id)

            elif not should_post:
                name = token.get("base_token_name", "Unknown")
                symbol = token.get("symbol", "Unknown")
                print(f"⚠️ Skipping pool (does not meet criteria): {name} ({symbol})")

        await asyncio.sleep(POLL_INTERVAL)

# -----------------------------
# RUN THE BOT
# -----------------------------
if __name__ == "__main__":
    asyncio.run(monitor_pools())
