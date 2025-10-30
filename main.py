import os, asyncio, aiohttp
from telethon import TelegramClient
from flask import Flask

# -------------------
# Keep-alive server
# -------------------
app = Flask("keep_alive")

@app.route("/")
def home():
    return "PumpFun Bot is alive ✅"

def keep_alive():
    app.run(host="0.0.0.0", port=5000)

# -------------------
# Bot setup
# -------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))

client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# -------------------
# Pump.fun fetch
# -------------------
async def fetch_pumpfun():
    url = "https://frontend-api.pump.fun/coins/leaderboard?sort=created&timeRange=1h&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            try:
                return await r.json()
            except:
                return []

# -------------------
# Simple honeypot filter
# -------------------
def is_honeypot(text):
    blocked = ["max sell", "cannot sell", "trapped", "no sell", "dev control", "rug"]
    return any(b in text.lower() for b in blocked)

# -------------------
# Monitor coins
# -------------------
async def monitor():
    seen = set()
    while True:
        try:
            data = await fetch_pumpfun()
            if not data:
                print("⚠️ No data from Pump.fun API")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Loop over coins
            for coin in data:
                mint = coin.get("mint")
                symbol = coin.get("symbol")
                buying = coin.get("buyTxCount", 0)
                selling = coin.get("sellTxCount", 0)

                if not mint or mint in seen:
                    continue
                seen.add(mint)

                if buying > 0 and selling > 0:  # Only coins that have trading activity
                    message = (
                        f"🔥 *New Tradable Coin*\n"
                        f"💠 Symbol: `{symbol}`\n"
                        f"🧬 Mint: `{mint}`\n"
                        f"📈 Buy Tx: {buying}\n"
                        f"📉 Sell Tx: {selling}\n"
                        f"🔗 https://pump.fun/{mint}"
                    )
                    await client.send_message(TELEGRAM_CHAT, message, parse_mode="md")
                    print(f"✅ Posted: {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

# -------------------
# Run bot + keep-alive
# -------------------
keep_alive()
print("✅ Bot started + keep-alive running")

async def main():
    await monitor()

client.loop.run_until_complete(main())
