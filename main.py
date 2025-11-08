#!/usr/bin/env python3
"""
Combo Meme Coin Scanner
- Dexscreener: early pair detection across many chains
- CoinGecko: momentum low-cap detection
- Posts to a Telegram channel via Telethon
- Flask keep-alive for Render
"""
import os
import asyncio
import requests
import json
import threading
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
from flask import Flask

# -----------------------------
# CONFIG / ENV
# -----------------------------
UTC = timezone.utc

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003219642022"))  # default to your channel
POSTED_FILE = os.getenv("POSTED_FILE", "posted_coins.json")
PORT = int(os.environ.get("PORT", "10000"))

DEX_CHAINS = ["solana", "base", "bsc", "ethereum", "arbitrum", "polygon"]
SCAN_INTERVAL_SECONDS = 10 * 60
CG_PER_PAGE = 50
CG_PAGES = 3

CG_VOLUME_MIN = 100_000
CG_VOLUME_MAX = 200_000
CG_MARKET_CAP_MAX = 5_000_000
CG_MOMENTUM_24H_MIN = 5.0
CG_MOMENTUM_1H_MIN = 2.0

DEX_LIQUIDITY_MIN = 1_000
DEX_LIQUIDITY_MAX = 200_000
DEX_MIN_BUYS_H1 = 1

# -----------------------------
# Persistence: posted history
# -----------------------------
if os.path.exists(POSTED_FILE):
    try:
        with open(POSTED_FILE, "r") as f:
            POSTED = json.load(f)
    except Exception:
        POSTED = []
else:
    POSTED = []

POSTED_SET = set(POSTED)

def save_posted():
    try:
        with open(POSTED_FILE, "w") as f:
            json.dump(list(POSTED_SET), f)
    except Exception as e:
        print(f"[{datetime.now(UTC)}] ❌ Failed to save posted file: {e}")

def mark_posted(key):
    POSTED_SET.add(key)
    save_posted()

# -----------------------------
# Telethon client
# -----------------------------
client = TelegramClient("combo_meme_session", API_ID, API_HASH)

# -----------------------------
# Flask keep-alive
# -----------------------------
app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def home():
    return "✅ Meme Coin Combo Scanner Running"

def run_web():
    app.run(host="0.0.0.0", port=PORT, threaded=True)

# -----------------------------
# Utilities
# -----------------------------
def now_str():
    return datetime.now(UTC).isoformat()

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

# -----------------------------
# Dexscreener functions
# -----------------------------
DEX_BASE = "https://api.dexscreener.com/latest/dex/pairs/{}"

def scan_dex_chain(chain):
    try:
        r = requests.get(DEX_BASE.format(chain), timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("pairs", []) if isinstance(data, dict) else []
    except Exception as e:
        print(f"[{now_str()}] ❌ Dexscreener fetch failed for {chain}: {e}")
        return []

async def fetch_dex_new_pairs_all_chains():
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, scan_dex_chain, chain) for chain in DEX_CHAINS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {chain: res if not isinstance(res, Exception) else [] for chain, res in zip(DEX_CHAINS, results)}

def dex_pair_key(chain, pair):
    addr = pair.get("pairAddress") or pair.get("pair")
    if addr:
        return f"dex:{chain}:{addr}"
    base = safe_get(pair, "baseToken", "address") or safe_get(pair, "baseToken", "symbol") or "unknown"
    quote = safe_get(pair, "quoteToken", "address") or safe_get(pair, "quoteToken", "symbol") or "unknown"
    return f"dex:{chain}:{base}/{quote}"

def format_dex_message(chain, pair):
    base = safe_get(pair, "baseToken", "symbol") or safe_get(pair, "baseToken", "name") or "UNKNOWN"
    name = safe_get(pair, "baseToken", "name") or base
    price = pair.get("priceUsd")
    liquidity = safe_get(pair, "liquidity", "usd", default=0) or pair.get("liquidityUsd", 0) or 0
    buys_h1 = safe_get(pair, "txns", "h1", "buys", default=0)
    sells_h1 = safe_get(pair, "txns", "h1", "sells", default=0)
    pair_url = pair.get("dexUrl") or pair.get("url") or pair.get("pairUrl") or ""
    pair_created = pair.get("pairCreatedAt") or pair.get("createdAt") or None
    age_str = "unknown"
    if pair_created:
        try:
            dt = datetime.fromtimestamp(int(pair_created), tz=UTC)
            age = datetime.now(UTC) - dt
            if age < timedelta(minutes=1):
                age_str = f"{int(age.total_seconds())}s"
            elif age < timedelta(hours=1):
                age_str = f"{int(age.total_seconds()//60)}m"
            else:
                age_str = f"{int(age.total_seconds()//3600)}h"
        except Exception:
            age_str = "unknown"
    msg = (
        f"🧪 New Pair Detected ({chain.upper()})\n"
        f"{name} ({base})\n"
        f"Price: ${price if price is not None else 'N/A'} | Liquidity: ${int(liquidity):,}\n"
        f"Buys(1h): {buys_h1} | Sells(1h): {sells_h1} | Age: {age_str}\n"
        f"{pair_url}\n\n⚠️ Early-stage token — DYOR before interacting."
    )
    return msg

# -----------------------------
# CoinGecko functions
# -----------------------------
CG_BASE = "https://api.coingecko.com/api/v3/coins/markets"

def fetch_coingecko_markets(per_page=CG_PER_PAGE, total_pages=CG_PAGES):
    all_coins = []
    for page in range(1, total_pages + 1):
        params = {
            "vs_currency": "usd",
            "order": "market_cap_asc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "1h,24h"
        }
        try:
            r = requests.get(CG_BASE, params=params, timeout=20)
            r.raise_for_status()
            all_coins.extend(r.json())
        except Exception as e:
            print(f"[{now_str()}] ❌ CoinGecko fetch error page {page}: {e}")
    return all_coins

def cg_coin_key(coin):
    return f"cg:{coin.get('id')}"

def format_cg_message(coin):
    name = coin.get("name")
    symbol = (coin.get("symbol") or "").upper()
    volume = coin.get("total_volume", 0) or 0
    market_cap = coin.get("market_cap", 0) or 0
    p1 = coin.get("price_change_percentage_1h_in_currency") or 0
    p24 = coin.get("price_change_percentage_24h_in_currency") or 0
    cg_link = f"https://www.coingecko.com/en/coins/{coin.get('id')}"
    msg = (
        f"🚀 {name} ({symbol})\n"
        f"Volume: ${int(volume):,} | Market Cap: ${int(market_cap):,}\n"
        f"1h Gain: {p1:.2f}% | 24h Gain: {p24:.2f}%\n"
        f"{cg_link}\n\n⚠️ Informational only. DYOR."
    )
    return msg

# -----------------------------
# Scanning & posting
# -----------------------------
async def process_dexscreener():
    posted_count = 0
    try:
        pairs_by_chain = await fetch_dex_new_pairs_all_chains()
        for chain, pairs in pairs_by_chain.items():
            for p in pairs:
                key = dex_pair_key(chain, p)
                if key in POSTED_SET:
                    continue
                liquidity = safe_get(p, "liquidity", "usd", default=0) or p.get("liquidityUsd") or 0
                buys_h1 = safe_get(p, "txns", "h1", "buys", default=0)
                if not (DEX_LIQUIDITY_MIN <= float(liquidity) <= DEX_LIQUIDITY_MAX):
                    continue
                if buys_h1 < DEX_MIN_BUYS_H1:
                    continue
                msg = format_dex_message(chain, p)
                try:
                    await client.send_message(CHANNEL_ID, msg)
                    mark_posted(key)
                    posted_count += 1
                except Exception as e:
                    print(f"[{now_str()}] ❌ Failed to post dex pair {key}: {e}")
                if posted_count >= 10:
                    break
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f"[{now_str()}] ❌ process_dexscreener error: {e}")
    return posted_count

async def process_coingecko():
    posted_count = 0
    try:
        loop = asyncio.get_running_loop()
        coins = await loop.run_in_executor(None, fetch_coingecko_markets)
        candidates = []
        for coin in coins:
            key = cg_coin_key(coin)
            volume = coin.get("total_volume", 0) or 0
            market_cap = coin.get("market_cap", 0) or 0
            p1 = coin.get("price_change_percentage_1h_in_currency") or 0
            p24 = coin.get("price_change_percentage_24h_in_currency") or 0
            if not (CG_VOLUME_MIN <= volume <= CG_VOLUME_MAX):
                continue
            if key in POSTED_SET:
                continue
            if (p24 < CG_MOMENTUM_24H_MIN) and (p1 < CG_MOMENTUM_1H_MIN):
                continue
            if market_cap > CG_MARKET_CAP_MAX:
                continue
            candidates.append((coin, max(p24, p1)))
        candidates.sort(key=lambda x: x[1], reverse=True)
        for coin, _ in candidates[:7]:
            key = cg_coin_key(coin)
            msg = format_cg_message(coin)
            try:
                await client.send_message(CHANNEL_ID, msg)
                mark_posted(key)
                posted_count += 1
            except Exception as e:
                print(f"[{now_str()}] ❌ Failed to post coingecko coin {key}: {e}")
    except Exception as e:
        print(f"[{now_str()}] ❌ process_coingecko error: {e}")
    return posted_count

# -----------------------------
# Combined scheduler
# -----------------------------
async def combo_scan_loop():
    while True:
        try:
            print(f"[{now_str()}] ⏱️ Combo scan started...")
            dex_task = asyncio.create_task(process_dexscreener())
            cg_task = asyncio.create_task(process_coingecko())
            results = await asyncio.gather(dex_task, cg_task)
            dex_posted, cg_posted = results
            if dex_posted == 0 and cg_posted == 0:
                try:
                    await client.send_message(CHANNEL_ID,
                        "❌ No new meme coins found with volume $100k–$200k and positive momentum."
                    )
                except Exception as e:
                    print(f"[{now_str()}] ❌ Failed to post no-results message: {e}")
            print(f"[{now_str()}] ✅ Combo scan completed.")
        except Exception as e:
            print(f"[{now_str()}] ❌ Combo scan error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

# -----------------------------
# Manual trigger via /signal
# -----------------------------
@client.on(events.NewMessage(pattern="/signal"))
async def manual_trigger(event):
    try:
        await event.reply("⏳ Manual combo scan started — running Dexscreener + CoinGecko...")
        dex_task = asyncio.create_task(process_dexscreener())
        cg_task = asyncio.create_task(process_coingecko())
        results = await asyncio.gather(dex_task, cg_task)
        await event.reply("✅ Manual scan completed.")
        if sum(results) == 0:
            await event.reply("❌ No new meme coins found with volume $100k–$200k and positive momentum.")
    except Exception as e:
        await event.reply(f"❌ Manual scan error: {e}")

# -----------------------------
# Main startup
# -----------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{now_str()}] ✅ Combo Meme Coin Scanner is live")
    asyncio.create_task(combo_scan_loop())
    await client.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"[{now_str()}] Bot stopped manually")
    except Exception as e:
        print(f"[{now_str()}] ❌ Fatal error: {e}")
