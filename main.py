import os, asyncio, aiohttp, re
from telethon import TelegramClient
from keep_alive import keep_alive

keep_alive()
print("✅ Bot online + Keep alive started")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
LOWCAP_THRESHOLD_MC = int(os.getenv("LOWCAP_THRESHOLD_MC", "5000"))

client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

X_KEYWORDS = ["pump", "moon", "viral", "sol", "memecoin", "trending"]

async def fetch_pumpfun():
    url = "https://pump.fun/leaderboard?tab=new"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            return await r.text()

def is_honeypot(text):
    blocked = ["max sell", "cannot sell", "trapped", "no sell", "dev control"]
    return any(b in text.lower() for b in blocked)

async def check_x_hype(name):
    url = f"https://nitter.net/search?f=tweets&q={name}+sol"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            t = await r.text()
            return any(k in t.lower() for k in X_KEYWORDS)

async def monitor():
    sent = set()
    while True:
        try:
            html = await fetch_pumpfun()
            tokens = re.findall(r'"mint":"(.*?)".*?"symbol":"(.*?)"', html)

            for mint, symbol in tokens[:10]:
                if mint in sent: continue
                sent.add(mint)

                # Fake call to mc below, replace with Birdeye later if you get key
                mc = 3000

                desc = f"{symbol} on pump.fun"

                if is_honeypot(desc):
                    continue

                hype = await check_x_hype(symbol)

                msg = f"🔥 NEW MEME COIN\n{symbol}\nMint: {mint}\nMC: ~${mc}\nHype: {'✅ X Buzz' if hype else '❌ none yet'}\nhttps://pump.fun/{mint}"

                if mc < LOWCAP_THRESHOLD_MC or hype:
                    await client.send_message(TELEGRAM_CHAT, msg)
                    print("✅ Posted:", symbol)

        except Exception as e:
            print("Error:", e)

        await asyncio.sleep(POLL_INTERVAL)


async def main():
    await monitor()

client.loop.run_until_complete(main())
