#!/usr/bin/env python3
"""
Combo Meme Coin Scanner (Updated, Safe Version)
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
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003219642022"))  # public channel
POSTED_FILE = os.getenv("POSTED_FILE", "posted_coins.json")
PORT = int(os.environ.get("PORT", "10000"))

SCAN_INTERVAL_SECONDS = 10 * 60  # every 10 minutes

DEX_TRENDING_URL = "https://api.dexscreener.com/latest/dex/trending"
DEX_LIQUIDITY_MIN = 1_000
DEX_LIQUIDITY_MAX = 200_000
DEX_MIN_BUYS_H1 = 1
DEX_MAX_AGE_HOURS = 24
DEX_TOP_N = 3

CG_BASE = "https://api.coingecko.com/api/v3/coins/markets"
CG_PER_PAGE = 50
CG_PAGES = 1
CG_PAGE_DELAY = 2
CG_VOLUME_MIN = 100_000
CG_VOLUME_MAX = 200_000
CG_MARKET_CAP_MAX = 5_000_000
CG_MOMENTUM_24H_MIN = 5.0
CG_MOMENTUM_1H_MIN = 2.0

# -----------------------------
# Persistence
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
        print(f"[save_posted] ❌ {e}")


def mark_posted(key):
    POSTED_SET.add(key)
    save_posted()


# -----------------------------
# Telethon & Flask setup
# -----------------------------
client = TelegramClient("combo_meme_session", API_ID, API_HASH)
app = Flask(__name__)


@app.route("/", methods=["GET", "HEAD"])
def home():
    return "✅ Meme Coin Combo Scanner Running"


def run_web():
    app.run(host="0.0.0.0", port=PORT, threaded=True)


# -----------------------------
# Utils
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
# Dexscreener Fetch (403 Safe)
# -----------------------------
def dex_trending_fetch():
    """Fetch trending feed from Dexscreener safely (bypass 403)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CoinScanner/1.0; +https://t.me/)",
        "Accept": "application/json",
    }
    try:
        r = requests.get(DEX_TRENDING_URL, headers=headers, timeout=15)
        if r.status_code == 403:
            print(f"[{now_str()}] ⚠️ Dexscreener blocked request (403). Retrying via alternate path...")
            alt_url = "https://api.dexscreener.com/latest/dex/search?q=trending"
            r = requests.get(alt_url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "pairs" in data:
            return data["pairs"]
        if isinstance(data, list):
            return data
        for v in data.values() if isinstance(data, dict) else []:
            if isinstance(v, list):
                return v
        return []
    except Exception as e:
        print(f"[{now_str()}] ❌ Dexscreener trending fetch failed: {e}")
        return []


# -----------------------------
# Dexscreener processing
# -----------------------------
def dex_pair_unique_key(pair):
    addr = pair.get("pairAddress") or pair.get("pair")
    if addr:
        return f"dex:{addr}"
    chain = pair.get("chain") or "unknown"
    base = safe_get(pair, "baseToken", "symbol", default="base")
    quote = safe_get(pair, "quoteToken", "symbol", default="quote")
    return f"dex:{chain}:{base}/{quote}"


def dex_pair_age_hours(pair):
    ts = pair.get("pairCreatedAt") or pair.get("createdAt")
    if not ts:
        return None
    try:
        dt = datetime.fromtimestamp(int(ts), tz=UTC)
        return (datetime.now(UTC) - dt).total_seconds() / 3600
    except Exception:
        return None


def dex_pair_volume(pair):
    v = safe_get(pair, "volume", "h24") or safe_get(pair, "liquidity", "usd", default=0)
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0


def format_dex_trending_msg(pair):
    chain = pair.get("chain", "unknown").upper()
    sym = safe_get(pair, "baseToken", "symbol", default="N/A")
    name = safe_get(pair, "baseToken", "name", default=sym)
    price = pair.get("priceUsd") or "N/A"
    liq = safe_get(pair, "liquidity", "usd", default=0)
    vol = safe_get(pair, "volume", "h24", default=0)
    p1 = safe_get(pair, "priceChange", "h1", default=0)
    p24 = safe_get(pair, "priceChange", "h24", default=0)
    url = pair.get("dexUrl") or ""
    created = pair.get("pairCreatedAt")
    if created:
        try:
            dt = datetime.fromtimestamp(int(created), tz=UTC)
            launch = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            launch = "unknown"
    else:
        launch = "unknown"
    return (
        f"🚀 New Meme Pair (<24h) — {chain}\n"
        f"{name} ({sym})\n"
        f"💰 Price: ${price} | Vol(24h): ${int(float(vol)):,} | Liq: ${int(float(liq)):,}\n"
        f"📈 1h/24h: {float(p1):.2f}% / {float(p24):.2f}%\n"
        f"🕒 Launch: {launch}\n"
        f"{url}\n\n⚠️ DYOR — Early token."
    )


async def process_dex_trending():
    posted = 0
    try:
        pairs = await asyncio.to_thread(dex_trending_fetch)
        if not pairs:
            return 0
        candidates = []
        for p in pairs:
            key = dex_pair_unique_key(p)
            if key in POSTED_SET:
                continue
            age = dex_pair_age_hours(p)
            if age is None or age > DEX_MAX_AGE_HOURS:
                continue
            liq = safe_get(p, "liquidity", "usd", default=0)
            buys = safe_get(p, "txns", "h1", "buys", default=0)
            try:
                liq = float(liq)
            except Exception:
                liq = 0.0
            if not (DEX_LIQUIDITY_MIN <= liq <= DEX_LIQUIDITY_MAX):
                continue
            if int(buys) < DEX_MIN_BUYS_H1:
                continue
            score = dex_pair_volume(p)
            candidates.append((score, key, p))
        if not candidates:
            return 0
        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, key, pair in candidates[:DEX_TOP_N]:
            msg = format_dex_trending_msg(pair)
            await client.send_message(CHANNEL_ID, msg)
            mark_posted(key)
            posted += 1
        return posted
    except Exception as e:
        print(f"[{now_str()}] ❌ process_dex_trending error: {e}")
        return 0


# -----------------------------
# CoinGecko backup
# -----------------------------
def fetch_coingecko_markets():
    all_coins = []
    for page in range(1, CG_PAGES + 1):
        params = {
            "vs_currency": "usd",
            "order": "market_cap_asc",
            "per_page": CG_PER_PAGE,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "1h,24h",
        }
        try:
            r = requests.get(CG_BASE, params=params, timeout=15)
            r.raise_for_status()
            all_coins.extend(r.json())
        except Exception as e:
            print(f"[CoinGecko] ❌ {e}")
        asyncio.sleep(CG_PAGE_DELAY)
    return all_coins


async def process_coingecko_momentum():
    posted = 0
    try:
        coins = await asyncio.to_thread(fetch_coingecko_markets)
        candidates = []
        for c in coins:
            key = f"cg:{c.get('id')}"
            if key in POSTED_SET:
                continue
            vol = c.get("total_volume", 0)
            mc = c.get("market_cap", 0)
            p1 = c.get("price_change_percentage_1h_in_currency") or 0
            p24 = c.get("price_change_percentage_24h_in_currency") or 0
            if not (CG_VOLUME_MIN <= vol <= CG_VOLUME_MAX):
                continue
            if mc > CG_MARKET_CAP_MAX:
                continue
            if (p24 < CG_MOMENTUM_24H_MIN) and (p1 < CG_MOMENTUM_1H_MIN):
                continue
            candidates.append((max(p24, p1), key, c))
        if not candidates:
            return 0
        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, key, coin in candidates[:3]:
            msg = (
                f"📈 CoinGecko Momentum\n"
                f"{coin['name']} ({coin['symbol'].upper()})\n"
                f"Vol: ${int(coin['total_volume']):,} | MC: ${int(coin['market_cap']):,}\n"
                f"1h/24h: {p1:.2f}% / {p24:.2f}%\n"
                f"https://www.coingecko.com/en/coins/{coin['id']}\n\n⚠️ DYOR."
            )
            await client.send_message(CHANNEL_ID, msg)
            mark_posted(key)
            posted += 1
        return posted
    except Exception as e:
        print(f"[{now_str()}] ❌ process_coingecko_momentum error: {e}")
        return 0


# -----------------------------
# Scan Loop
# -----------------------------
async def combo_scan_loop():
    while True:
        try:
            print(f"[{now_str()}] ⏱️ Combo scan started...")
            dex_posted, cg_posted = await asyncio.gather(
                process_dex_trending(), process_coingecko_momentum()
            )
            total = (dex_posted or 0) + (cg_posted or 0)
            if total == 0:
                print(f"[{now_str()}] ❌ No new meme coins found.")
            print(f"[{now_str()}] ✅ Combo scan completed. Posted {total} items.")
        except Exception as e:
            print(f"[{now_str()}] ❌ Combo scan error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


# -----------------------------
# /signal manual command
# -----------------------------
@client.on(events.NewMessage(pattern="/signal"))
async def manual_trigger(event):
    try:
        await event.reply("⏳ Manual combo scan running...")
        dex_posted, cg_posted = await asyncio.gather(
            process_dex_trending(), process_coingecko_momentum()
        )
        total = (dex_posted or 0) + (cg_posted or 0)
        if total == 0:
            await event.reply("❌ No new meme coins found.")
        else:
            await event.reply(f"✅ Manual scan done. Posted {total} items.")
    except Exception as e:
        await event.reply(f"❌ Manual scan error: {e}")


# -----------------------------
# MAIN
# -----------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{now_str()}] ✅ Combo Meme Coin Scanner is live.")
    asyncio.create_task(combo_scan_loop())
    await client.run_until_disconnected()


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
