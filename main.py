import os, asyncio, aiohttp, json, re
from telethon import TelegramClient
from keep_alive import keep_alive

# Start keep-alive server (for Render / Replit)
keep_alive()
print("✅ Bot started + keep-alive running")

# Environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
LOWCAP_THRESHOLD_MC = int(os.getenv("LOWCAP_THRESHOLD_MC", "5000"))

client = TelegramClient("pumpfun", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# X trend keywords
X_KEYWORDS = ["pump", "moon", "sol", "memecoin", "crypto", "trending", "🐸", "🚀"]

# ✅ Get live new coins from pumpportal
async def fetch_pumpfun():
    url = "https://pumpportal.fun/api/data/all_coins"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://pump.fun"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            try:
                return await r.json()
            except:
                return []

# ✅ Simple honeypot screening (can upgrade later)
def is_honeypot(name):
    block = ["max sell", "cannot sell", "no sell", "trap", "rug"]
    return any(b in name.lower() for b in block)

# ✅ Check hype on X via Nitter
async def check_x(symbol):
    url = f"https://nitter.net/search?f=tweets&q={symbol}+sol"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as r:
                text = await r.text()
                return any(k in text.lower() for k in X_KEYWORDS)
        except:
            return False

async def monitor():
    seen = set()

    while True:
        try:
            data = await fetch_pumpfun()

            # Only take top 20 recent
            tokens = data[:20]

            for coin in tokens:
                mint = coin.get("mint")
                symbol = coin.get("symbol") or "UNKNOWN"

                if not mint or mint in seen:
                    continue

                seen.add(mint)

                # Placeholder MC (You can add Birdeye API later)
                mc = 3000  

                hype = await check_x(symbol)

                # Skip obvious rugs
                if is_honeypot(symbol):
                    print(f"⛔ Rug filter: {symbol}")
                    continue

                msg = (
                    f"🔥 *NEW PUMP.FUN MEME*\n"
                    f"💠 Symbol: `{symbol}`\n"
                    f"🧬 Mint: `{mint}`\n"
                    f"💰 MC: ~${mc}\n"
                    f"📈 X Buzz: {'✅ Active' if hype else '❌ None yet'}\n"
                    f"🔗 https://pump.fun/{mint}"
                )

                # Conditions to post
                if mc < LOWCAP_THRESHOLD_MC or hype:
                    await client.send_message(TELEGRAM_CHAT, msg, parse_mode="md")
                    print(f"✅ Posted: {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        print("⏳ Scanning new coins...")
        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

client.loop.run_until_complete(main())
