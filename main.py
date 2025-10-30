import os, asyncio, aiohttp, re
from telethon import TelegramClient
from keep_alive import keep_alive
from bs4 import BeautifulSoup

# Start keep-alive web server
keep_alive()
print("✅ Bot started + Keep alive running")

# ENV VARS
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))

client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

BASE_URL = "https://pump.fun/coins/leaderboard?sort=created&timeRange=1h&limit=50"

async def fetch_html(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            return await r.text()

def has_buy_sell(html):
    """Check if the coin has both buy and sell transactions"""
    soup = BeautifulSoup(html, "html.parser")
    buy = soup.find_all(text=re.compile("buy", re.I))
    sell = soup.find_all(text=re.compile("sell", re.I))
    return len(buy) > 0 and len(sell) > 0

async def monitor():
    seen = set()
    while True:
        try:
            html = await fetch_html(BASE_URL)
            tokens = re.findall(r'"mint":"(.*?)".*?"symbol":"(.*?)"', html)

            for mint, symbol in tokens[:20]:  # limit 20 coins per scan
                if mint in seen:
                    continue
                seen.add(mint)

                coin_url = f"https://pump.fun/{mint}"
                coin_html = await fetch_html(coin_url)

                if has_buy_sell(coin_html):
                    msg = f"🔥 Active Coin\n💠 {symbol}\n🧬 Mint: {mint}\n🔗 {coin_url}"
                    await client.send_message(TELEGRAM_CHAT, msg)
                    print(f"✅ Posted: {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

client.loop.run_until_complete(main())
