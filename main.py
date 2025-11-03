import os, time, requests, asyncio
from datetime import datetime
from telethon import TelegramClient

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")  # @channelusername or ID

GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10

seen = {}

client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def send_msg(text):
    try:
        await client.send_message(CHANNEL, text)
        print("✅ Alert sent")
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")

def fetch_pools():
    r = requests.get(GECKO_URL, timeout=10)
    return r.json().get("data", [])

async def monitor():
    print("✅ Solana Gem Hunter Bot Running...")

    while True:
        print(f"[{datetime.now()}] ℹ️ Checking pools... seen={len(seen)}")

        try:
            pools = fetch_pools()
        except Exception as e:
            print(f"[{datetime.now()}] ⚠️ Gecko Error: {e}")
            await asyncio.sleep(POLL_DELAY)
            continue

        for p in pools:
            attrs = p.get("attributes", {})
            token = attrs.get("base_token_name")
            symbol = attrs.get("base_token_symbol")
            pool_id = p.get("id")

            tx = int(attrs.get("txn_count", 0) or 0)
            vol = attrs.get("volume_usd", 0)
            if isinstance(vol, dict):
                vol = vol.get("h24", 0)
            vol = float(vol or 0)

            # First appearance
            if pool_id not in seen:
                seen[pool_id] = tx
                print(f"🆕 New token spotted: {symbol} | tx={tx} vol={vol}")

                if tx >= 1 and vol >= 5000:
                    print(f"📊 Matched gem criteria — sending alert: {symbol}")
                    await send_msg(
                        f"🆕 **NEW SOL GEM FOUND**\n\n"
                        f"💎 Token: {symbol} ({token})\n"
                        f"💰 Volume: ${round(vol,2)}\n"
                        f"📈 Txns: {tx}\n"
                        f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                continue

            # spike detection
            prev_tx = seen[pool_id]
            if tx > prev_tx + 3:
                print(f"🚀 Spike detected: {symbol} | tx {prev_tx} -> {tx}")
                await send_msg(
                    f"🚨 **SPIKE ALERT**\n\n"
                    f"💎 Token: {symbol} ({token})\n"
                    f"📈 Txns: {tx} (+{tx-prev_tx})\n"
                    f"💰 Volume: ${round(vol,2)}\n"
                    f"📊 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
                )

            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

async def main():
    await monitor()

client.loop.run_until_complete(main())
