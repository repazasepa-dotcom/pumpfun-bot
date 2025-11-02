#!/usr/bin/env python3
"""
Meme Pro Watcher + Keep-Alive + X/Twitter Hype

- Detects new Solana meme coins (GeckoTerminal)
- Volume >= $50k
- Tracks holder growth (Solscan)
- Estimates Twitter/X hype (Nitter)
- Posts high-score coins to Telegram
- Runs 24/7 with Flask keep-alive
"""

import os
import json
import asyncio
from datetime import datetime
import aiohttp
from telethon import TelegramClient
from flask import Flask
import threading
import time

# ---------------------------
# Config
# ---------------------------
TELETHON_SESSION = os.getenv("TELETHON_SESSION", "meme_pro_session")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEST_CHANNEL = os.getenv("DEST_CHANNEL", "@PumpFunMemeCoinAlert")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "120"))
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "50000"))
MIN_HOLDERS = int(os.getenv("MIN_HOLDERS", "50"))
NITTER_MENTIONS_THRESHOLD = int(os.getenv("NITTER_MENTIONS_THRESHOLD", "50"))
POST_SCORE_THRESHOLD = int(os.getenv("POST_SCORE_THRESHOLD", "3"))
SEEN_STORE = os.getenv("SEEN_STORE", "seen_tokens.json")

# ---------------------------
# Flask Keep-Alive
# ---------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Meme Pro Bot Running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Keep-alive web server running on port {port}")
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ---------------------------
# Seen tokens store
# ---------------------------
def load_seen():
    if os.path.exists(SEEN_STORE):
        try:
            with open(SEEN_STORE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_seen(d):
    with open(SEEN_STORE, "w") as f:
        json.dump(d, f, indent=2)

# ---------------------------
# Telegram Client
# ---------------------------
client = TelegramClient(TELETHON_SESSION, API_ID, API_HASH)

async def send_telegram_message(text):
    try:
        await client.send_message(DEST_CHANNEL, text, parse_mode="markdown")
    except Exception as e:
        print("Telegram send error:", e)

# ---------------------------
# GeckoTerminal fetcher
# ---------------------------
async def fetch_geckoterminal_new_pools(session):
    url = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
    try:
        async with session.get(url, timeout=20) as resp:
            if resp.status != 200:
                print("GeckoTerminal status:", resp.status)
                return []
            data = await resp.json()
            return data.get("data", [])
    except Exception as e:
        print("GeckoTerminal fetch error:", e)
        return []

# ---------------------------
# Holder count via Solscan
# ---------------------------
async def get_holder_count_solscan(session, token_address):
    url = f"https://public-api.solscan.io/token/meta?tokenAddress={token_address}"
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return 0
            j = await resp.json()
            holders = j.get("holder") or j.get("holders") or j.get("holderCount") or 0
            if not holders and isinstance(j.get("data"), dict):
                d = j.get("data")
                holders = d.get("holder") or d.get("holders") or d.get("holderCount") or 0
            return int(holders or 0)
    except:
        return 0

# ---------------------------
# Twitter/X hype estimate via Nitter
# ---------------------------
async def nitter_mentions_count(session, query):
    q = query.replace(" ", "+")
    url = f"https://nitter.net/search?f=tweets&q={q}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MemeWatcher/1.0)"}
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return 0
            text = await resp.text()
            count = text.count('<div class="tweet')
            if count == 0:
                count = text.count('class="timeline-item"')
            if count == 0:
                count = text.count('/status/')
            return count
    except:
        return 0

# ---------------------------
# Score token
# ---------------------------
async def score_token(session, pool_record):
    attr = pool_record.get("attributes", {}) if isinstance(pool_record, dict) else {}
    token_address = attr.get("base_token_address") or ""
    token_symbol = attr.get("base_token_symbol") or ""
    token_name = attr.get("base_token_name") or ""
    pool_address = attr.get("address") or ""
    volume = 0.0
    try:
        volume = float(attr.get("volume_usd") or attr.get("volume") or 0)
    except:
        volume = 0.0

    holders = 0
    if token_address:
        holders = await get_holder_count_solscan(session, token_address)

    mentions = 0
    query = token_symbol or token_name
    if query:
        mentions = await nitter_mentions_count(session, query)

    score = 0
    if volume >= MIN_VOLUME_USD:
        score += 1
    if holders >= MIN_HOLDERS:
        score += 1
    if mentions >= NITTER_MENTIONS_THRESHOLD:
        score += 1

    return {
        "address": token_address,
        "symbol": token_symbol,
        "name": token_name,
        "pool": pool_address,
        "volume": volume,
        "holders": holders,
        "mentions": mentions,
        "score": score,
        "raw": pool_record
    }

# ---------------------------
# Message formatter
# ---------------------------
def build_message(info):
    name = info.get("name") or "-"
    sym = info.get("symbol") or "-"
    addr = info.get("address") or "-"
    pool = info.get("pool") or "-"
    vol = info.get("volume") or 0
    holders = info.get("holders") or 0
    mentions = info.get("mentions") or 0
    score = info.get("score") or 0
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    solscan = f"https://solscan.io/token/{addr}" if addr else ""
    chart = f"https://www.geckoterminal.com/solana/pools/{pool}" if pool else ""
    msg = (
f"🚀 *New Solana Meme Coin*\n\n"
f"*{name}* `{sym}`\n"
f"• Score: {score}\n"
f"• Volume: ${vol:,.0f}\n"
f"• Holders: {holders}\n"
f"• Mentions (est): {mentions}\n\n"
f"• Chart: {chart}\n"
f"• Token: {solscan}\n\n"
f"_Detected at {ts}_"
    )
    return msg

# ---------------------------
# Main polling loop
# ---------------------------
async def poll_loop():
    seen = load_seen()
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                print(f"[{datetime.utcnow().isoformat()}] Checking GeckoTerminal new pools...")
                pools = await fetch_geckoterminal_new_pools(session)
                candidates = []
                for p in pools:
                    attr = p.get("attributes", {}) if isinstance(p, dict) else {}
                    try:
                        vol = float(attr.get("volume_usd") or attr.get("volume") or 0)
                    except:
                        vol = 0
                    if vol < MIN_VOLUME_USD:
                        continue
                    info = await score_token(session, p)
                    addr = (info.get("address") or "").lower()
                    if not addr or addr in seen:
                        continue
                    if info.get("score", 0) >= POST_SCORE_THRESHOLD:
                        candidates.append(info)
                candidates.sort(key=lambda x: (x.get("score",0), x.get("volume",0)), reverse=True)
                for cand in candidates:
                    msg = build_message(cand)
                    await send_telegram_message(msg)
                    seen[cand["address"].lower()] = datetime.utcnow().isoformat()
                    save_seen(seen)
                    await asyncio.sleep(1.5)
            except Exception as e:
                print("Main loop error:", e)
            await asyncio.sleep(POLL_INTERVAL)

# ---------------------------
# Entrypoint
# ---------------------------
async def main():
    print("Starting Meme Pro Bot with Keep-Alive. Posting to:", DEST_CHANNEL)
    await client.start(bot_token=BOT_TOKEN)
    await poll_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user.")
