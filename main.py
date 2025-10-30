import os
import asyncio
import aiohttp
from telethon import TelegramClient
from keep_alive import keep_alive

# Start keep-alive
keep_alive()
print("✅ Bot online + Keep alive started")

# ----------------------------
# ENVIRONMENT VARIABLES
# ----------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3"))  # Check every 3 seconds

# Telegram client
client = TelegramClient('pumpfun', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ----------------------------
# Fetch Pump.fun transactions
# ----------------------------
async def fetch_transactions():
    url = "https://frontend-api.pump.fun/transactions?limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            try:
                return await resp.json()
            except:
                return []

# ----------------------------
# Monitor transactions
# ----------------------------
async def monitor():
    seen_tx = set()  # Keep track of transactions

    while True:
        try:
            data = await fetch_transactions()
            if not data:
                print("⚠️ No data returned from Pump.fun API")
                await asyncio.sleep(POLL_INTERVAL)
                continue

            for tx in data:
                tx_id = tx.get("id")
                symbol = tx.get("coinSymbol")
                mint = tx.get("coinMint")
                tx_type = tx.get("type")  # 'buy' or 'sell'
                amount = tx.get("amount", 0)

                if tx_id in seen_tx:
                    continue
                seen_tx.add(tx_id)

                message = (
                    f"💥 New Transaction!\n"
                    f"💠 Coin: `{symbol}`\n"
                    f"🧬 Mint: `{mint}`\n"
                    f"📊 Type: {tx_type.upper()}\n"
                    f"💰 Amount: {amount}\n"
                    f"🔗 https://pump.fun/{mint}"
                )

                await client.send_message(TELEGRAM_CHAT, message, parse_mode="md")
                print(f"✅ Posted {symbol} {tx_type} transaction")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

# ----------------------------
# Run bot
