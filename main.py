import os, time, requests, asyncio, threading
from flask import Flask
from telethon import TelegramClient, events

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
POLL_DELAY = 10

seen = {}

# ---------------- TELETHON BOT ----------------
client = TelegramClient("bot", API_ID, API_HASH)

@client.on(events.NewMessage(pattern="/ping"))
async def ping(event):
    await event.reply("✅ I'm alive and monitoring SOL markets!")

async def send_alert(text):
    try:
        await client.send_message(CHAT_ID, text)
        print("✅ Alert sent")
    except Exception as e:
        print("❌ Telegram error:", e)

def fetch_pools():
    r = requests.get(GECKO_URL, timeout=10)
    return r.json().get("data", [])

async def monitor():
    print("✅ Solana Volume Bot Live")

    while True:
        try:
            pools = fetch_pools()
        except Exception as e:
            print("⚠️ GeckoTerminal error:", e)
            await asyncio.sleep(POLL_DELAY)
            continue

        for p in pools:
            attr = p.get("attributes", {})
            pool_id = p.get("id")
            token = attr.get("base_token_name")
            sym = attr.get("base_token_symbol")
            tx = int(attr.get("txn_count") or 0)
            vol = float(attr.get("volume_usd", 0) or 0)

            if pool_id not in seen:
                seen[pool_id] = tx

                # ✅ New token low volume
                if tx <= 1 and vol <= 5000:
                    await send_alert(
                        f"🆕 *New SOL Meme Detected*\n"
                        f"{sym} | {token}\n"
                        f"Txns: {tx}\n"
                        f"Volume: ${vol}\n"
                        f"https://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                continue

            prev = seen[pool_id]

            # ✅ Sudden volume or txn spike
            if tx > prev + 1 and vol >= 5000:
                await send_alert(
                    f"🚨 *Pump Signal*\n"
                    f"{sym} | {token}\n"
                    f"New Txns: {tx} (+{tx-prev})\n"
                    f"Volume: ${vol}\n"
                    f"https://www.geckoterminal.com/solana/pools/{pool_id}"
                )

            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

async def start_bot():
    await client.start(bot_token=BOT_TOKEN)
    await monitor()

def run_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())

# ---------------- WEB KEEP-ALIVE ----------------
app = Flask(__name__)

@app.route("/")
def alive():
    return "✅ Bot online"

# ---------------- START THREADS ----------------
threading.Thread(target=run_async_loop).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
