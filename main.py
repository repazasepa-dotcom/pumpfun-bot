# main.py
import os
import time
import requests
import asyncio
import threading
from telethon import TelegramClient
from flask import Flask, Response

# -----------------------------
# ENV / CONFIG
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "")      # @yourchannel or -1001234567890
PORT = int(os.getenv("PORT", os.getenv("RENDER_PORT", "10000")))

GECKO_URL = os.getenv(
    "GECKO_POOLS_URL",
    "https://api.geckoterminal.com/api/v2/networks/solana/pools?include=base_token"
)
POLL_DELAY = int(os.getenv("POLL_DELAY", "10"))  # seconds

# thresholds
NEW_TXN = int(os.getenv("NEW_TXN", "1"))         # tx == 1
MAX_VOLUME = float(os.getenv("MAX_VOLUME", "5000"))  # <= $5,000
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", "50"))  # >= $50
PUMP_DELTA = int(os.getenv("PUMP_DELTA", "3"))    # +3 tx spike

# -----------------------------
# TELEGRAM CLIENT
# -----------------------------
client = TelegramClient("bot_session", API_ID, API_HASH)
client.start(bot_token=BOT_TOKEN)

# -----------------------------
# KEEP-ALIVE (Flask)
# -----------------------------
app = Flask("keepalive")

@app.route("/")
def health():
    return Response("OK ✅ Bot running", status=200)

def run_flask():
    # bind to provided PORT so Render / Replit detect it
    app.run(host="0.0.0.0", port=PORT, threaded=True)

# start flask in background thread
threading.Thread(target=run_flask, daemon=True).start()
print(f"🌐 Keep-alive web server running on 0.0.0.0:{PORT}")

# -----------------------------
# UTILS
# -----------------------------
def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return default

def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def fetch_pools_sync():
    """Synchronous requests to GeckoTerminal (called via asyncio.to_thread)."""
    try:
        r = requests.get(GECKO_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        print("⚠️ Gecko fetch error:", e)
        return []

async def send_telegram(text):
    try:
        await client.send_message(CHANNEL, text)
        print("✅ Sent:", text.splitlines()[0][:80])
    except Exception as e:
        print("❌ Telegram send error:", e)

# -----------------------------
# MONITOR LOGIC
# -----------------------------
seen = {}  # pool_id -> last_txn_count

async def monitor_loop():
    print("🚀 SOL Gem Hunter (GeckoTerminal) started — monitoring pools")
    while True:
        pools = await asyncio.to_thread(fetch_pools_sync)

        if not pools:
            await asyncio.sleep(POLL_DELAY)
            continue

        for pool in pools:
            attrs = pool.get("attributes", {}) or {}
            pool_id = pool.get("id")
            if not pool_id:
                continue

            # parse fields robustly
            tx = safe_int(attrs.get("txn_count") or attrs.get("txns") or 0, 0)

            volume = (
                attrs.get("volume_usd")
                or attrs.get("m5_volume_usd")
                or attrs.get("h1_volume_usd")
                or attrs.get("h24_volume_usd")
                or attrs.get("volume")
                or 0
            )
            volume = safe_float(volume, 0.0)

            # liquidity (reserve_usd, liquidity_usd, market_cap_usd fallback)
            liq = attrs.get("reserve_usd") or attrs.get("liquidity_usd") or attrs.get("market_cap_usd") or 0
            liq = safe_float(liq, 0.0)

            symbol = attrs.get("base_token_symbol") or attrs.get("symbol") or "UNKNOWN"
            name = attrs.get("base_token_name") or attrs.get("name") or ""

            # First time we see the pool: record tx and evaluate "newborn" condition
            if pool_id not in seen:
                seen[pool_id] = tx

                # Newborn token condition: TX == NEW_TXN AND volume <= MAX_VOLUME AND liquidity >= MIN_LIQUIDITY
                if tx == NEW_TXN and volume <= MAX_VOLUME and liq >= MIN_LIQUIDITY:
                    text = (
                        f"🆕 **NEW SOLANA GEM DETECTED**\n\n"
                        f"💎 Token: {symbol} — {name}\n"
                        f"📈 TXNs: {tx}\n"
                        f"💰 Volume: ${volume:,.2f}\n"
                        f"🌊 Liquidity: ${liq:,.2f}\n"
                        f"🔗 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
                    )
                    await send_telegram(text)
                    print("🚀 Newborn alert for", pool_id)

                continue  # don't process further on first sight

            prev_tx = safe_int(seen.get(pool_id, 0), 0)

            # Pump detection: transaction spike
            if tx >= prev_tx + PUMP_DELTA:
                text = (
                    f"🚨 **VOLUME SPIKE**\n\n"
                    f"💎 Token: {symbol} — {name}\n"
                    f"📈 TXNs: {tx} (Δ +{tx - prev_tx})\n"
                    f"💰 Volume: ${volume:,.2f}\n"
                    f"🌊 Liquidity: ${liq:,.2f}\n"
                    f"🔗 Chart: https://www.geckoterminal.com/solana/pools/{pool_id}"
                )
                await send_telegram(text)
                print("📈 Pump alert for", pool_id)

            # update last seen tx
            seen[pool_id] = tx

        await asyncio.sleep(POLL_DELAY)

# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":
    try:
        loop = client.loop
        loop.run_until_complete(monitor_loop())
    except KeyboardInterrupt:
        print("🛑 Stopped by user")
    except Exception as e:
        print("❌ Fatal error:", e)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
