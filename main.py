import os
import asyncio
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey
from telethon import TelegramClient
from keep_alive import keep_alive

# Start keep-alive web server
keep_alive()
print("✅ Keep-alive server started")

# Telegram Bot Config
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")

# Poll interval in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

# Initialize Telegram client
client = TelegramClient('solana_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Solana RPC client
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
sol_client = AsyncClient(SOLANA_RPC)

# Keep track of already seen token mints
seen_tokens = set()

async def fetch_new_tokens():
    """
    Placeholder: Scan Solana blockchain for new SPL tokens.
    This is simplified for demonstration purposes.
    """
    # Example: replace with real RPC calls to get new tokens
    # For testing, you can just simulate new tokens
    import random, string
    mint = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return [{"mint": mint, "symbol": f"TOKEN{mint}"}]

async def monitor():
    while True:
        try:
            tokens = await fetch_new_tokens()

            for token in tokens:
                mint = token["mint"]
                symbol = token["symbol"]

                if mint in seen_tokens:
                    continue
                seen_tokens.add(mint)

                # Compose Telegram message
                message = (
                    f"🔥 New Solana Token Detected\n"
                    f"💠 Symbol: {symbol}\n"
                    f"🧬 Mint: {mint}\n"
                    f"🔗 https://solscan.io/token/{mint}"
                )

                await client.send_message(TELEGRAM_CHAT, message)
                print(f"✅ Posted {symbol}")

        except Exception as e:
            print("⚠️ Error:", e)

        await asyncio.sleep(POLL_INTERVAL)

async def main():
    await monitor()

# Run the monitoring bot
client.loop.run_until_complete(main())
