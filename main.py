import os, asyncio, aiohttp, re
from telethon import TelegramClient
from keep_alive import keep_alive

# Start keep-alive web server
keep_alive()
print("✅ Bot online + Keep alive started")

# ENV VARS
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
LOWCAP_THRESHOLD_MC = int(os.getenv("LOWCAP_THRESHOLD_MC", "5000"))

client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

X_KEYWORDS = ["pump", "moon", "viral", "sol", "memecoin", "trending", "🐸", "🚀"]

# ✅ Pump.fun official API endpoint
async def fetch_pumpfun():
    url = "https://frontend-api.pump.fun/coins/leaderboard?sort=created&timeRange=1h&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            try:
                return await r.json()
            except:
                return []

# ✅ Basic honeypot text filter (upgradeable later)
def is_honeypot(text):
    blocked = ["max sell", "cannot sell", "trapped", "no sell", "dev control", "rug"]
    return any(b in text.lower() for b in blocked)

# ✅ X hype check (Nitter)
async def check_x_hype(name):
    url = f"https://nitter.net/search?f=tweets&q={name}+sol"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            t = await r.text()
            return any(k in t.lower() for k in X_KEYWORDS)

async def monitor():
    seen = set()

    while True:
        try:
            data = await fetch_pumpfun()
            if not data:
                print("⚠️ No data returned from Pump.fun API")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Token list (mint + symbol)
            tokens = [(x["mint"], x["symbol"]) for x in data if "mint" in x and "symbol" in x]

            for mint, symbol in tokens[:15]:
                if mint in seen: 
                    continue
                seen.add(mint)

                # Placeholder market cap (when no Birdeye key)
                mc = 3000  

                desc = f"{symbol} launched on pump.fun"
                if is_honeypot(desc):
                    print(f"❌ Honeypot filter triggered: {symbol}")
                    continue

                hype = await check_x_hype(symbol)
                
                message = (
                    f"🔥 *New Pump.fun Meme Coin*\n"
                    f"💠 Symbol: `{symbol}`\n"
                    f"🧬 Mint: `{mint}`\n"
                    f"💰 MC Estimate: ~${mc}\n"
                    f"📈 X Hype: {'✅ Active buzz' if hype else '❌ None'}\n"
                    f"🔗 https://pump.fun/{mint}"
                )

                if mc < LOWCAP_THRESHOLD_MC or hype:
                    await client.send_message(TELEGRAM_CHAT, message, parse_mode="md")
                    print(f"✅ Posted {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

client.loop.run_until_complete(main())
