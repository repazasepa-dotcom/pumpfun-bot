import os, asyncio, aiohttp
from telethon import TelegramClient
from keep_alive import keep_alive

keep_alive()
print("✅ Bot online + Keep alive started")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

client = TelegramClient("pumpfun", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def fetch_pumpfun():
    url = "https://frontend-api.pump.fun/coins/leaderboard?sort=created&timeRange=1h&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            try:
                return await resp.json()
            except:
                return []

async def monitor():
    seen = set()
    while True:
        print("⏳ Checking Pump.fun launches...")

        try:
            data = await fetch_pumpfun()
            for x in data:
                mint = x.get("mint")
                name = x.get("name")
                symbol = x.get("symbol")

                if not mint or mint in seen:
                    continue

                seen.add(mint)

                msg = (
                    f"🚨 *NEW Pump.fun Launch!*\n\n"
                    f"Name: *{name}*\n"
                    f"Symbol: `{symbol}`\n"
                    f"Mint: `{mint}`\n\n"
                    f"🔗 https://pump.fun/{mint}"
                )

                await client.send_message(TELEGRAM_CHAT, msg, parse_mode="md")
                print(f"✅ Sent: {symbol}")

        except Exception as e:
            print("❌ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

client.loop.run_until_complete(main())
