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

# Dexscreener chains to scan (common ones). 'all' chosen earlier => use these.
DEX_CHAINS = ["solana", "base", "bsc", "ethereum", "arbitrum", "polygon"]

# Scan interval (seconds) - user requested 10 minutes
SCAN_INTERVAL_SECONDS = 10 * 60

# CoinGecko pages/per_page (tunable)
CG_PER_PAGE = 50
CG_PAGES = 3

# Limits / filters
CG_VOLUME_MIN = 100_000
CG_VOLUME_MAX = 200_000
CG_MARKET_CAP_MAX = 5_000_000
CG_MOMENTUM_24H_MIN = 5.0  # percent
CG_MOMENTUM_1H_MIN = 2.0   # percent

# Dexscreener filters (example): liquidity/usd thresholds (tunable)
DEX_LIQUIDITY_MIN = 1_000    # $1k min liquidity to avoid dust
DEX_LIQUIDITY_MAX = 200_000  # broad upper bound, you can tune
DEX_MIN_BUYS_H1 = 1          # at least 1 buy in last hour (tunable)

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

# normalize to set for quick checks
POSTED_SET = set(POSTED)

def save_posted():
    # keep list form for readability
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
    # threaded to satisfy Render health checks
    app.run(host="0.0.0.0", port=PORT, threaded=True)

# -----------------------------
# Utilities
# -----------------------------
def now_str():
    return datetime.now(UTC).isoformat()

def safe_get(d, *keys, default=None):
    """Safe nested get for dicts — returns default if any key missing."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

# -----------------------------
# Dexscreener: fetch new pairs for given chain
# -----------------------------
DEX_BASE = "https://api.dexscreener.com/latest/dex/pairs/{}"  # chain slug

def scan_dex_chain(chain):
    """Synchronous fetch for a single chain's pairs from Dexscreener (used inside async wrapper)."""
    url = DEX_BASE.format(chain)
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        # Dexscreener returns top-level "pairs" list
        pairs = data.get("pairs", []) if isinstance(data, dict) else []
        return pairs
    except Exception as e:
        print(f"[{now_str()}] ❌ Dexscreener fetch failed for {chain}: {e}")
        return []

async def fetch_dex_new_pairs_all_chains():
    """Async wrapper that fetches for all configured chains concurrently (using threadpool)."""
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, scan_dex_chain, chain) for chain in DEX_CHAINS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    pairs_by_chain = {}
    for chain, res in zip(DEX_CHAINS, results):
        if isinstance(res, Exception):
            pairs_by_chain[chain] = []
        else:
            pairs_by_chain[chain] = res
    return pairs_by_chain

def dex_pair_key(chain, pair):
    """Create unique key for a pair to track posting history."""
    # Dexscreener provides 'pairAddress' or 'pair' fields; fallback to baseToken+quoteToken
    addr = pair.get("pairAddress") or pair.get("pair")
    if addr:
        return f"dex:{chain}:{addr}"
    # fallback:
    base = safe_get(pair, "baseToken", "address") or safe_get(pair, "baseToken", "symbol") or "unknown"
    quote = safe_get(pair, "quoteToken", "address") or safe_get(pair, "quoteToken", "symbol") or "unknown"
    return f"dex:{chain}:{base}/{quote}"

def format_dex_message(chain, pair):
    """Format Telegram message for a Dexscreener pair."""
    base = safe_get(pair, "baseToken", "symbol") or (safe_get(pair, "baseToken", "name") or "UNKNOWN")
    name = safe_get(pair, "baseToken", "name") or base
    price = pair.get("priceUsd")
    liquidity = safe_get(pair, "liquidity", "usd", default=0) or pair.get("liquidityUsd", 0) or 0
    buys_h1 = safe_get(pair, "txns", "h1", "buys", default=0)
    sells_h1 = safe_get(pair, "txns", "h1", "sells", default=0)
    pair_url = pair.get("dexUrl") or pair.get("url") or pair.get("pairUrl") or ""
    # pair creation time (if provided) — Dexscreener gives pairCreatedAt in seconds sometimes
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
# CoinGecko: fetch markets
# -----------------------------
CG_BASE = "https://api.coingecko.com/api/v3/coins/markets"

def fetch_coingecko_markets(per_page=CG_PER_PAGE, total_pages=CG_PAGES):
    """Sync fetch (wrapped in async) — returns list of coins"""
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
        # small delay to be polite (Rate limit safety)
        # we keep it synchronous inside this wrapper, sleep here minimally
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
# Scanning & posting logic
# -----------------------------
async def process_dexscreener():
    """Fetch Dexscreener pairs across chains and post qualifying new pairs."""
    try:
        pairs_by_chain = await fetch_dex_new_pairs_all_chains()
        posted_count = 0
        for chain, pairs in pairs_by_chain.items():
            # iterate newest-first if Dexscreener returns that ordering
            for p in pairs:
                key = dex_pair_key(chain, p)
                if key in POSTED_SET:
                    continue
                # liquidity detection (try a few fields)
                liquidity = safe_get(p, "liquidity", "usd", default=0) or p.get("liquidityUsd") or 0
                # volume last 24h (field may be volume.h24)
                volume_h24 = safe_get(p, "volume", "h24", default=0) or safe_get(p, "volume", "h24Usd", default=0) or 0
                # buys in last hour
                buys_h1 = safe_get(p, "txns", "h1", "buys", default=0)
                # quick filters:
                if liquidity is None:
                    liquidity = 0
                if volume_h24 is None:
                    volume_h24 = 0
                # apply filters to avoid dust & huge projects
                if not (DEX_LIQUIDITY_MIN <= float(liquidity) <= DEX_LIQUIDITY_MAX):
                    # skip pairs with too little or too much liquidity
                    continue
                if buys_h1 < DEX_MIN_BUYS_H1:
                    continue
                # Passed filters -> post
                msg = format_dex_message(chain, p)
                try:
                    await client.send_message(CHANNEL_ID, msg)
                    mark_posted(key)
                    posted_count += 1
                except Exception as e:
                    print(f"[{now_str()}] ❌ Failed to post dex pair {key}: {e}")
                # limit spam per run (tunable)
                if posted_count >= 10:
                    break
            # small pause between chains to avoid burst
            await asyncio.sleep(0.5)
        if posted_count == 0:
            # optional: no dex pairs found — we won't spam channel with every run
            pass
    except Exception as e:
        print(f"[{now_str()}] ❌ process_dexscreener error: {e}")

async def process_coingecko():
    """Fetch CoinGecko markets and post qualifying coins (momentum low-caps)."""
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
            # filters
            if not (CG_VOLUME_MIN <= volume <= CG_VOLUME_MAX):
                continue
            if key in POSTED_SET:
                continue
            if (p24 < CG_MOMENTUM_24H_MIN) and (p1 < CG_MOMENTUM_1H_MIN):
                continue
            if market_cap > CG_MARKET_CAP_MAX:
                continue
            candidates.append((coin, max(p24, p1)))
        # sort by best momentum
        candidates.sort(key=lambda x: x[1], reverse=True)
        posted = 0
        for coin, _score in candidates:
            key = cg_coin_key(coin)
            msg = format_cg_message(coin)
            try:
                await client.send_message(CHANNEL_ID, msg)
                mark_posted(key)
                posted += 1
            except Exception as e:
                print(f"[{now_str()}] ❌ Failed to post coingecko coin {key}: {e}")
            if posted >= 7:
                break
        if posted == 0:
            # send occasional no-results message? (disabled to avoid spam)
            # await client.send_message(CHANNEL_ID, "❌ No new meme coins found from CoinGecko this run.")
            pass
    except Exception as e:
        print(f"[{now_str()}] ❌ process_coingecko error: {e}")

# -----------------------------
# Combined scheduler
# -----------------------------
async def combo_scan_loop():
    """Main recurring task that runs Dexscreener + CoinGecko scans every interval."""
    while True:
        try:
            print(f"[{now_str()}] ⏱️ Combo scan started...")
            # run both scans concurrently
            await asyncio.gather(process_dexscreener(), process_coingecko())
            print(f"[{now_str()}] ✅ Combo scan completed.")
        except Exception as e:
            print(f"[{now_str()}] ❌ Combo scan error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

# -----------------------------
# Manual trigger via /signal
# -----------------------------
@client.on(events.NewMessage(pattern="/signal"))
async def manual_trigger(event):
    sender = event.sender_id
    try:
        await event.reply("⏳ Manual combo scan started — running Dexscreener + CoinGecko...")
        await asyncio.gather(process_dexscreener(), process_coingecko())
        await event.reply("✅ Manual scan completed.")
    except Exception as e:
        await event.reply(f"❌ Manual scan error: {e}")

# -----------------------------
# Main startup
# -----------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{now_str()}] ✅ Combo Meme Coin Scanner is live")
    # start the recurring combo scan
    asyncio.create_task(combo_scan_loop())
    await client.run_until_disconnected()

if __name__ == "__main__":
    # start web keep-alive thread for Render
    threading.Thread(target=run_web, daemon=True).start()
    # run Telethon + scanning
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"[{now_str()}] Bot stopped manually")
    except Exception as e:
        print(f"[{now_str()}] ❌ Fatal error: {e}")
