#!/usr/bin/env python3
"""
Combo Meme Coin Scanner (Updated)
- Dexscreener: uses trending feed to detect newly launched pairs (<24h)
- CoinGecko: momentum low-cap detection (backup)
- Posts top 3 new DexScreener pairs per scan to public channel
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
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003219642022"))  # public channel only
POSTED_FILE = os.getenv("POSTED_FILE", "posted_coins.json")
PORT = int(os.environ.get("PORT", "10000"))

# Scanning settings
SCAN_INTERVAL_SECONDS = 10 * 60  # 10 minutes

# CoinGecko (backup momentum) settings
CG_PER_PAGE = 50
CG_PAGES = 1   # keep small to avoid 429
CG_PAGE_DELAY = 2  # seconds delay between page requests

# Filters / thresholds
CG_VOLUME_MIN = 100_000
CG_VOLUME_MAX = 200_000
CG_MARKET_CAP_MAX = 5_000_000
CG_MOMENTUM_24H_MIN = 5.0
CG_MOMENTUM_1H_MIN = 2.0

DEX_LIQUIDITY_MIN = 1_000     # $1k
DEX_LIQUIDITY_MAX = 200_000   # $200k
DEX_MIN_BUYS_H1 = 1
DEX_MAX_AGE_HOURS = 24        # only <24h old for Dex trending posts
DEX_TOP_N = 3                 # post top 3 per scan

# Dexscreener trending endpoint
DEX_TRENDING_URL = "https://api.dexscreener.com/latest/dex/trending"

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

def dex_trending_fetch():
    """Fetch trending feed from Dexscreener (synchronous)."""
    try:
        r = requests.get(DEX_TRENDING_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        # Dexscreener trending may return dict with 'pairs' or a top-level list; handle both
        if isinstance(data, dict) and "pairs" in data:
            return data["pairs"]
        if isinstance(data, list):
            return data
        # fallback: try to find pairs in keys
        for v in data.values() if isinstance(data, dict) else []:
            if isinstance(v, list):
                return v
        return []
    except Exception as e:
        print(f"[{now_str()}] ❌ Dexscreener trending fetch failed: {e}")
        return []

# -----------------------------
# Dexscreener processing (trending)
# -----------------------------
def dex_pair_unique_key(pair):
    """Unique key for a pair from Dexscreener to avoid reposts."""
    # Prefer pairAddress or pair
    addr = pair.get("pairAddress") or pair.get("pair")
    if addr:
        return f"dex:{addr}"
    # fallback to chain + base + quote
    chain = pair.get("chain") or pair.get("chainName") or "unknown"
    base = safe_get(pair, "baseToken", "address") or safe_get(pair, "baseToken", "symbol") or "base"
    quote = safe_get(pair, "quoteToken", "address") or safe_get(pair, "quoteToken", "symbol") or "quote"
    return f"dex:{chain}:{base}/{quote}"

def dex_pair_age_hours(pair):
    """Return age in hours if pairCreatedAt exists, else None."""
    pair_created = pair.get("pairCreatedAt") or pair.get("createdAt") or None
    if not pair_created:
        return None
    try:
        ts = int(pair_created)
        dt = datetime.fromtimestamp(ts, tz=UTC)
        age = datetime.now(UTC) - dt
        return age.total_seconds() / 3600.0
    except Exception:
        return None

def dex_pair_volume(pair):
    """Prefer volume.h24 or liquidity as ranking metric (float)."""
    v = safe_get(pair, "volume", "h24") or safe_get(pair, "volume", "h24Usd") or safe_get(pair, "volumeUsd", None)
    if not v:
        # fallback to liquidity usd
        v = safe_get(pair, "liquidity", "usd") or pair.get("liquidityUsd") or 0
    try:
        return float(v)
    except Exception:
        try:
            return float(str(v).replace(",", ""))
        except Exception:
            return 0.0

def format_dex_trending_msg(pair):
    chain = pair.get("chain") or pair.get("chainName") or "unknown"
    base_sym = safe_get(pair, "baseToken", "symbol") or safe_get(pair, "baseToken", "name") or "UNKNOWN"
    base_name = safe_get(pair, "baseToken", "name") or base_sym
    price = pair.get("priceUsd")
    liquidity = safe_get(pair, "liquidity", "usd", default=0) or pair.get("liquidityUsd") or 0
    vol24 = safe_get(pair, "volume", "h24", default=0) or safe_get(pair, "volume", "h24Usd", default=0) or 0
    p1 = safe_get(pair, "priceChange", "h1") or safe_get(pair, "priceChange1h") or 0
    p24 = safe_get(pair, "priceChange", "h24") or safe_get(pair, "priceChange24h") or 0
    pair_url = pair.get("dexUrl") or pair.get("url") or pair.get("pairUrl") or ""
    pair_created = pair.get("pairCreatedAt") or pair.get("createdAt") or None
    launch_time = "unknown"
    if pair_created:
        try:
            dt = datetime.fromtimestamp(int(pair_created), tz=UTC)
            launch_time = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
    msg = (
        f"🚀 New Meme Pair (<24h) — {chain.upper()}\n"
        f"{base_name} ({base_sym})\n"
        f"Price: ${price if price is not None else 'N/A'} | Volume(24h): ${int(float(vol24)):,} | Liquidity: ${int(float(liquidity)):,}\n"
        f"1h / 24h: {float(p1):.2f}% / {float(p24):.2f}%\n"
        f"Launch: {launch_time}\n"
        f"{pair_url}\n\n⚠️ Extremely early-stage token — DYOR before interacting."
    )
    return msg

async def process_dex_trending():
    """
    Fetch trending feed, filter newly launched (<24h), apply liquidity/buys filters,
    rank by 24h volume and post top N to public channel.
    Returns number posted.
    """
    posted = 0
    try:
        # fetch trending pairs
        loop = asyncio.get_running_loop()
        pairs = await loop.run_in_executor(None, dex_trending_fetch)
        if not pairs:
            return 0

        # filter & score
        candidates = []
        for p in pairs:
            # unique key
            key = dex_pair_unique_key(p)
            if key in POSTED_SET:
                continue
            # age < 24h
            age_h = dex_pair_age_hours(p)
            if age_h is None or age_h > DEX_MAX_AGE_HOURS:
                continue
            # liquidity & buys
            liquidity = safe_get(p, "liquidity", "usd", default=0) or p.get("liquidityUsd") or 0
            buys_h1 = safe_get(p, "txns", "h1", "buys", default=0) or safe_get(p, "txns", "h1Buys", default=0) or 0
            try:
                liquidity_val = float(liquidity)
            except Exception:
                liquidity_val = 0.0
            if not (DEX_LIQUIDITY_MIN <= liquidity_val <= DEX_LIQUIDITY_MAX):
                continue
            if int(buys_h1) < DEX_MIN_BUYS_H1:
                continue
            # use 24h volume or liquidity to score
            score = dex_pair_volume(p)
            candidates.append((score, key, p))

        if not candidates:
            return 0

        # top by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:DEX_TOP_N]

        # post each
        for score, key, pair in top:
            msg = format_dex_trending_msg(pair)
            try:
                await client.send_message(CHANNEL_ID, msg)
                mark_posted(key)
                posted += 1
            except Exception as e:
                print(f"[{now_str()}] ❌ Failed to post trending pair {key}: {e}")

        return posted
    except Exception as e:
        print(f"[{now_str()}] ❌ process_dex_trending error: {e}")
        return 0

# -----------------------------
# CoinGecko (backup momentum)
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
        # polite delay to avoid 429
        try:
            asyncio.sleep(CG_PAGE_DELAY)
        except Exception:
            pass
    return all_coins

def cg_coin_key(coin):
    return f"cg:{coin.get('id')}"

def format_cg_msg(coin):
    name = coin.get("name")
    symbol = (coin.get("symbol") or "").upper()
    volume = coin.get("total_volume", 0) or 0
    market_cap = coin.get("market_cap", 0) or 0
    p1 = coin.get("price_change_percentage_1h_in_currency") or 0
    p24 = coin.get("price_change_percentage_24h_in_currency") or 0
    cg_link = f"https://www.coingecko.com/en/coins/{coin.get('id')}"
    msg = (
        f"📈 CoinGecko Momentum\n"
        f"{name} ({symbol})\n"
        f"Volume: ${int(volume):,} | Market Cap: ${int(market_cap):,}\n"
        f"1h / 24h: {p1:.2f}% / {p24:.2f}%\n"
        f"{cg_link}\n\n⚠️ Informational only. DYOR."
    )
    return msg

async def process_coingecko_momentum():
    posted = 0
    try:
        loop = asyncio.get_running_loop()
        coins = await loop.run_in_executor(None, fetch_coingecko_markets)
        candidates = []
        for coin in coins:
            key = cg_coin_key(coin)
            if key in POSTED_SET:
                continue
            vol = coin.get("total_volume", 0) or 0
            market_cap = coin.get("market_cap", 0) or 0
            p1 = coin.get("price_change_percentage_1h_in_currency") or 0
            p24 = coin.get("price_change_percentage_24h_in_currency") or 0
            if not (CG_VOLUME_MIN <= vol <= CG_VOLUME_MAX):
                continue
            if (p24 < CG_MOMENTUM_24H_MIN) and (p1 < CG_MOMENTUM_1H_MIN):
                continue
            if market_cap > CG_MARKET_CAP_MAX:
                continue
            # score by max(p24,p1)
            candidates.append((max(p24, p1), key, coin))
        if not candidates:
            return 0
        candidates.sort(key=lambda x: x[0], reverse=True)
        # post up to 3 (backup)
        for score, key, coin in candidates[:3]:
            msg = format_cg_msg(coin)
            try:
                await client.send_message(CHANNEL_ID, msg)
                mark_posted(key)
                posted += 1
            except Exception as e:
                print(f"[{now_str()}] ❌ Failed to post CoinGecko coin {key}: {e}")
        return posted
    except Exception as e:
        print(f"[{now_str()}] ❌ process_coingecko_momentum error: {e}")
        return 0

# -----------------------------
# Combined scheduler
# -----------------------------
async def combo_scan_loop():
    while True:
        try:
            print(f"[{now_str()}] ⏱️ Combo scan started...")
            # run dex trending and cg momentum concurrently
            dex_task = asyncio.create_task(process_dex_trending())
            cg_task = asyncio.create_task(process_coingecko_momentum())
            dex_posted, cg_posted = await asyncio.gather(dex_task, cg_task)
            total = (dex_posted or 0) + (cg_posted or 0)
            if total == 0:
                # Only post the no-results message in public channel
                try:
                    await client.send_message(CHANNEL_ID, "❌ No new meme coins found with volume $100k–$200k and positive momentum.")
                except Exception as e:
                    print(f"[{now_str()}] ❌ Failed to post no-results message: {e}")
            print(f"[{now_str()}] ✅ Combo scan completed. Posted {total} items.")
        except Exception as e:
            print(f"[{now_str()}] ❌ Combo scan error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

# -----------------------------
# Manual /signal
# -----------------------------
@client.on(events.NewMessage(pattern="/signal"))
async def manual_trigger(event):
    try:
        await event.reply("⏳ Manual combo scan started — running Dexscreener (trending) + CoinGecko...")
        dex_posted, cg_posted = await asyncio.gather(process_dex_trending(), process_coingecko_momentum())
        total = (dex_posted or 0) + (cg_posted or 0)
        if total == 0:
            await event.reply("❌ No new meme coins found with volume $100k–$200k and positive momentum.")
        else:
            await event.reply(f"✅ Manual scan completed. Posted {total} items.")
    except Exception as e:
        await event.reply(f"❌ Manual scan error: {e}")

# -----------------------------
# Main
# -----------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{now_str()}] ✅ Combo Meme Coin Scanner is live")
    # start background scanner
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
