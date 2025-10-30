import os, asyncio, aiohttp
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

client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ✅ Pump.fun API endpoint
async def fetch_pumpfun():
    url = "https://frontend-api.pump.fun/coins/leaderboard?sort=created&timeRange=1h&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            try:
                return await r.json()
            except:
                return []

# ✅ Monitor coins (post every coin)
async def monitor():
    seen = set()

    while True:
        try:
            data = await fetch_pumpfun()
            if not data:
                print("⚠️ No data returned from Pump.fun API")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Post every coin
            tokens = [(x["mint"], x["symbol"]) for x in data if "mint" in x and "symbol" in x]

            for mint, symbol in tokens:
                if mint in seen: 
                    continue
                seen.add(mint)

                message = (
                    f"🔥 *New Pump.fun Meme Coin*\n"
                    f"💠 Symbol: `{symbol}`\n"
                    f"🧬 Mint: `{mint}`\n"
                    f"🔗 https://pump.fun/{mint}"
                )

                await client.send_message(TELEGRAM_CHAT, message, parse_mode="md")
                print(f"✅ Posted {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

client.loop.run_until_complete(main())
