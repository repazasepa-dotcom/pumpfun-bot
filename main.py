import os
import asyncio
import aiohttp
from aiohttp import web
from telegram import Bot

# -----------------------------
# CONFIG
# -----------------------------
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", "10000"))
GECKO_URL = "https://api.geckoterminal.com/api/v2/networks/solana/pools"
POLL_DELAY = 10

bot = Bot(TOKEN)
seen_tx = {}  # track previous txn count


# -----------------------------
# SEND TELEGRAM MESSAGE
# -----------------------------
async def send_alert(symbol, name, pool_id, txns, mcap):
    text = (
        f"🚨 **Pump Alert Detected!**\n\n"
        f"Token: {symbol} | {name}\n"
        f"New Txns: {txns}\n"
        f"Market Cap: ${mcap:,.2f}\n"
        f"Pool: `{pool_id}`\n\n"
        f"🔗 Chart:\nhttps://www.geckoterminal.com/solana/pools/{pool_id}"
    )

    try:
        await asyncio.get_event_loop().run_in_executor(
            None, bot.send_message, CHAT_ID, text, "Markdown"
        )
        print(f"✅ Alert sent: {symbol}")
    except Exception as e:
        print(f"❌ Telegram error:", e)


# -----------------------------
# MONITOR GECKOTERMINAL
# -----------------------------
async def monitor():
    async with aiohttp.ClientSession() as session:
        print("✅ Bot started — Tracking SOL pools...")

        while True:
            try:
                async with session.get(GECKO_URL, timeout=10) as r:
                    data = await r.json()
                    pools = data.get("data", [])
            except Exception as e:
                print("⚠️ Error fetching Gecko:", e)
                await asyncio.sleep(POLL_DELAY)
                continue

            for p in pools:
                attrs = p.get("attributes", {})
                pool_id = p.get("id")

                txns = int(attrs.get("txns", 0))
                mcap = float(attrs.get("fdv_usd") or 0)

                # skip if no value
                if pool_id not in seen_tx:
                    seen_tx[pool_id] = txns
                    continue

                prev = seen_tx[pool_id]

                # alert on new volume signal
                if txns > prev and txns >= 1:
                    symbol = attrs.get("base_token_symbol", "Unknown")
                    name = attrs.get("base_token_name", "Unknown")
                    await send_alert(symbol, name, pool_id, txns, mcap)

                seen_tx[pool_id] = txns

            await asyncio.sleep(POLL_DELAY)


# -----------------------------
# RENDER KEEP-ALIVE
# -----------------------------
async def health(request):
    return web.Response(text="OK")

async def start_app():
    asyncio.create_task(monitor())
    app = web.Application()
    app.router.add_get("/", health)
    return app


if __name__ == "__main__":
    web.run_app(start_app(), host="0.0.0.0", port=PORT)
