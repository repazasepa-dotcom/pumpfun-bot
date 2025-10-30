import os, asyncio, aiohttp
from telethon import TelegramClient
from keep_alive import keep_alive

# Start keep-alive
keep_alive()
print("✅ Bot started + keep-alive running")

# --- ENV VARS ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds

# Telegram client
client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# --- Monitor Pump.fun buy/sell transactions ---
async def fetch_transactions():
    url = "https://frontend-api.pump.fun/coins/leaderboard?sort=created&timeRange=1h&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            try:
                return await r.json()
            except:
                return []

async def monitor():
    seen = set()

    while True:
        try:
            data = await fetch_transactions()
            if not data:
                print("⚠️ No data returned from Pump.fun API")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            for coin in data:
                mint = coin.get("mint")
                symbol = coin.get("symbol")
                if not mint or mint in seen:
                    continue
                seen.add(mint)

                # Dummy MC (replace with actual API if needed)
                mc = 3000

                # Compose message
                message = (
                    f"🔥 *New Coin Activity*\n"
                    f"💠 Symbol: `{symbol}`\n"
                    f"🧬 Mint: `{mint}`\n"
                    f"💰 MC: ~${mc}\n"
                    f"🔗 https://pump.fun/{mint}"
                )

                # Send message to Telegram
                await client.send_message(TELEGRAM_CHAT, message, parse_mode="md")
                print(f"✅ Posted: {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

client.loop.run_until_complete(main())
