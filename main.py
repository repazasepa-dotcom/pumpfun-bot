import os
import asyncio
import aiohttp
from telethon import TelegramClient
from keep_alive import keep_alive

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # seconds
MAX_MARKETCAP = int(os.getenv("MAX_MARKETCAP", "10000000"))  # USD

# -----------------------------
# Telegram client
# -----------------------------
client = TelegramClient('meme_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# -----------------------------
# Keep-alive
# -----------------------------
keep_alive()
print("✅ Bot online + keep-alive started")

# -----------------------------
# Meme coin detection
# -----------------------------
MEME_KEYWORDS = ["doge", "shiba", "pepe", "moon", "lil", "baby"]
SEEN_COINS = set()
HONEYPOT_KEYWORDS = ["max sell", "cannot sell", "trapped", "no sell", "dev control", "rug"]

# -----------------------------
# Async CoinGecko fetch
# -----------------------------
async def fetch_new_coins(session):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_asc",
        "per_page": 50,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h"
    }
    try:
        async with session.get(url, params=params, timeout=15) as r:
            data = await r.json()
    except Exception as e:
        print("⚠️ CoinGecko API error:", e)
        return []

    meme_candidates = []
    for coin in data:
        name_symbol = f"{coin['name'].lower()} {coin['symbol'].lower()}"
        if any(k in name_symbol for k in MEME_KEYWORDS):
            if coin.get('market_cap') and coin['market_cap'] <= MAX_MARKETCAP:
                meme_candidates.append(coin)
    return meme_candidates

# -----------------------------
# Async social hype check
# -----------------------------
async def check_social_hype(session, name, symbol):
    try:
        url = f"https://nitter.net/search?f=tweets&q={name}+{symbol}"
        async with session.get(url, timeout=10) as r:
            text = await r.text()
            hype_keywords = ["🚀", "moon", "to the moon", "shill", "bullish"]
            return any(k in text.lower() for k in hype_keywords)
    except:
        return False

# -----------------------------
# Send Telegram alert
# -----------------------------
async def send_alert(session, coin):
    if coin['id'] in SEEN_COINS:
        return
    SEEN_COINS.add(coin['id'])

    hype = await check_social_hype(session, coin['name'], coin['symbol'])

    msg = (
        f"🚀 *Meme Coin Alert!*\n"
        f"💠 Name: {coin['name']} ({coin['symbol'].upper()})\n"
        f"💰 Price: ${coin['current_price']:,}\n"
        f"📊 Market Cap: ${coin['market_cap']:,}\n"
        f"📈 24h Change: {coin.get('price_change_percentage_24h', 0):.2f}%\n"
        f"📢 Social Hype: {'✅ Active buzz' if hype else '❌ None'}\n"
        f"🔗 CoinGecko: https://www.coingecko.com/en/coins/{coin['id']}"
    )
    await client.send_message(CHAT_ID, msg, parse_mode='md')
    print(f"✅ Alert sent for {coin['name']}")

# -----------------------------
# Monitor loop
# -----------------------------
async def monitor():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                coins = await fetch_new_coins(session)
                if coins:
                    print(f"⏳ Found {len(coins)} meme coin candidates")
                for coin in coins:
                    await send_alert(session, coin)
            except Exception as e:
                print("⚠️ Monitor error:", e)
            await asyncio.sleep(POLL_INTERVAL)

# -----------------------------
# Run bot
# -----------------------------
async def main():
    await monitor()

client.loop.run_until_complete(main())
