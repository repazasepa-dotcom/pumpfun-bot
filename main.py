#!/usr/bin/env python3
# PumpFun scout -> scrapes pump.fun table, scores coins, posts likely pumps to Telegram
# Requirements: telethon, flask, requests, beautifulsoup4
# Add to Render env: API_ID, API_HASH, BOT_TOKEN, CHANNEL, POLL_DELAY (optional), SCORE_THRESHOLD (optional)

import os
import time
import threading
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient
from flask import Flask

# ---------------------------
# Config (environment)
# ---------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "")  # e.g. @mychannel or -100123456...
POLL_DELAY = float(os.getenv("POLL_DELAY", "30"))  # seconds
PUMPFUN_URL = os.getenv("PUMPFUN_URL", "https://pump.fun/?view=table&coins_sort=created_timestamp")
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "65"))  # 0-100
MAX_AGE_MIN = float(os.getenv("MAX_AGE_MIN", "60"))  # minutes considered "recent"
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; PumpFunScout/1.0)")

# scoring weights (tweakable via env if desired)
W_RECENCY = float(os.getenv("W_RECENCY", "30"))
W_TXNS    = float(os.getenv("W_TXNS", "25"))
W_VOLUME  = float(os.getenv("W_VOLUME", "25"))
W_LIQUID  = float(os.getenv("W_LIQUID", "10"))   # lower liquidity increases score
W_HOLDERS = float(os.getenv("W_HOLDERS", "10"))  # lower holders increases score

# ---------------------------
# Init services
# ---------------------------
client = TelegramClient("pumpfun_bot", API_ID, API_HASH)
app = Flask("pumpfun_keepalive")

# simple in-memory state to avoid duplicate posts
posted = set()   # set of pool identifiers we've already posted
seen_time = {}   # pool_id -> last seen timestamp

# ---------------------------
# Utility parsing helpers
# ---------------------------
def safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        # remove commas, $ etc
        s = str(x).strip()
        s = re.sub(r"[^\d.\-]", "", s)
        if s == "" or s == "-" or s == ".":
            return default
        return float(s)
    except Exception:
        return default

def safe_int(x, default=0):
    try:
        return int(float(safe_float(x, default)))
    except Exception:
        return default

def parse_iso_or_timestamp(txt: str) -> Optional[float]:
    """
    Try to parse a created timestamp shown in the table.
    Returns epoch seconds or None.
    Handles ISO or relative times like '2m', '1h', 'just now' or explicit datetime strings.
    """
    if not txt:
        return None
    s = txt.strip().lower()
    now = datetime.now(timezone.utc)
    # common relative patterns: 'just now', '2m', '10s', '1h'
    if "just" in s or "now" in s:
        return now.timestamp()
    m = re.match(r"(\d+)\s*s", s)
    if m:
        return (now.timestamp() - int(m.group(1)))
    m = re.match(r"(\d+)\s*m", s)
    if m:
        return (now.timestamp() - int(m.group(1)) * 60)
    m = re.match(r"(\d+)\s*h", s)
    if m:
        return (now.timestamp() - int(m.group(1)) * 3600)
    # try numeric unix timestamp
    m = re.match(r"^\d{10,}$", s)
    if m:
        try:
            return float(s)
        except: 
            return None
    # try common datetime formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%b %d, %Y %H:%M"):
        try:
            dt = datetime.strptime(txt, fmt)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass
    return None

# ---------------------------
# Scoring function
# ---------------------------
def score_coin(age_minutes, txns, volume_usd, liquidity_usd, holders):
    """
    Score 0-100 where higher means more likely to pump (heuristic).
    age_minutes: coin age in minutes (lower -> higher recency score)
    txns: number of transactions
    volume_usd: 24h volume
    liquidity_usd: pool liquidity (higher liquidity reduces risk)
    holders: number of holders (higher holders reduces risk)
    """
    # recency score: coins younger than MAX_AGE_MIN get higher score
    recency = max(0.0, (MAX_AGE_MIN - age_minutes) / MAX_AGE_MIN) * 100  # 0..100
    recency = max(0.0, min(100.0, recency))

    # txns score: saturate at, say, 50 txns
    tx_score = min(100.0, (txns / 50.0) * 100.0)

    # volume score: saturate at $100k
    vol_score = min(100.0, (volume_usd / 100000.0) * 100.0)

    # liquidity impact: low liquidity -> bonus (we invert liquidity)
    liq_norm = min(1.0, liquidity_usd / 10000.0)  # 0..1
    liq_score = (1.0 - liq_norm) * 100.0

    # holders impact: fewer holders -> bonus
    holders_norm = min(1.0, holders / 200.0)
    holders_score = (1.0 - holders_norm) * 100.0

    # weighted sum
    weighted = (
        W_RECENCY * recency +
        W_TXNS * tx_score +
        W_VOLUME * vol_score +
        W_LIQUID * liq_score +
        W_HOLDERS * holders_score
    )
    # normalize by sum of weights
    total_weights = W_RECENCY + W_TXNS + W_VOLUME + W_LIQUID + W_HOLDERS
    if total_weights <= 0:
        return 0.0
    return (weighted / total_weights)

# ---------------------------
# Scrape Pump.Fun table
# ---------------------------
def scrape_pumpfun_table():
    """
    Fetch the page and parse table rows into dicts.
    We try to be flexible about table structure.
    Returns list of dict: [{id, name, symbol, created, txns, volume, liquidity, holders}, ...]
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(PUMPFUN_URL, headers=headers, timeout=12)
        r.raise_for_status()
        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # find first table (flexible)
        table = soup.find("table")
        rows = []
        if not table:
            # fallback: find rows of items (cards)
            items = soup.select(".coin-row, .table-row, .pool-row")
            for it in items:
                try:
                    name = it.select_one(".name, .coin-name")
                    symbol = it.select_one(".symbol")
                    created = it.select_one(".created, .age")
                    txns = it.select_one(".txns, .txn-count, .tx-count")
                    volume = it.select_one(".volume, .vol")
                    liq = it.select_one(".liquidity, .liq")
                    holders = it.select_one(".holders")
                    rows.append({
                        "id": it.get("data-id") or it.get("id") or None,
                        "name": (name.text.strip() if name else None),
                        "symbol": (symbol.text.strip() if symbol else None),
                        "created": (created.text.strip() if created else None),
                        "txns": (txns.text.strip() if txns else None),
                        "volume": (volume.text.strip() if volume else None),
                        "liquidity": (liq.text.strip() if liq else None),
                        "holders": (holders.text.strip() if holders else None)
                    })
                except Exception:
                    continue
            return rows

        # parse header -> column mapping
        ths = [th.get_text(strip=True).lower() for th in table.select("thead th")]
        # fallback if header absent
        colmap = {}
        for i, th in enumerate(ths):
            if "name" in th or "token" in th:
                colmap["name"] = i
            elif "symbol" in th:
                colmap["symbol"] = i
            elif "created" in th or "age" in th:
                colmap["created"] = i
            elif "txn" in th or "txns" in th or "tx" in th:
                colmap["txns"] = i
            elif "volume" in th or "vol" in th:
                colmap["volume"] = i
            elif "liquidity" in th or "liq" in th:
                colmap["liquidity"] = i
            elif "holders" in th or "holder" in th:
                colmap["holders"] = i
            elif "id" in th:
                colmap["id"] = i

        # parse rows
        for tr in table.select("tbody tr"):
            tds = tr.select("td")
            if not tds:
                continue
            def get_col(key):
                idx = colmap.get(key)
                if idx is None or idx >= len(tds):
                    return None
                return tds[idx].get_text(strip=True)
            # attempt to find a link or data-id for pool id
            pid = tr.get("data-id") or tr.get("id")
            if not pid:
                a = tr.find("a", href=True)
                if a and "/pools/" in a["href"]:
                    pid = a["href"].split("/")[-1]
            rows.append({
                "id": pid,
                "name": get_col("name"),
                "symbol": get_col("symbol"),
                "created": get_col("created"),
                "txns": get_col("txns"),
                "volume": get_col("volume"),
                "liquidity": get_col("liquidity"),
                "holders": get_col("holders"),
            })
        return rows
    except Exception as e:
        print("⚠️ scrape error:", e)
        return []

# ---------------------------
# Main analysis loop
# ---------------------------
async def monitor_loop():
    print("🚀 PumpFun scout started — scraping:", PUMPFUN_URL)
    while True:
        try:
            rows = scrape_pumpfun_table()
            now_ts = datetime.now().timestamp()
            for row in rows:
                pool_id = row.get("id") or (row.get("symbol") or row.get("name"))
                # parse numeric fields
                txns = safe_int(row.get("txns"))
                vol = safe_float(row.get("volume"))
                liq = safe_float(row.get("liquidity"))
                holders = safe_int(row.get("holders"))

                # parse created -> age in minutes
                created_ts = parse_iso_or_timestamp(row.get("created") or "")
                if created_ts:
                    age_min = max(0.0, (now_ts - created_ts) / 60.0)
                else:
                    # fallback: if not available, assume older
                    age_min = 99999.0

                # compute score
                score = score_coin(age_min, txns, vol, liq, holders)
                # debug log
                print(f"[{datetime.now()}] {row.get('symbol') or row.get('name')} id={pool_id} txns={txns} vol={vol} liq={liq} holders={holders} age_min={age_min:.1f} score={score:.1f}")

                # decide whether to post
                if pool_id and pool_id not in posted and score >= SCORE_THRESHOLD:
                    # compose message
                    title = row.get("symbol") or row.get("name") or pool_id
                    msg = (
                        f"🚨 *Potential Pump Candidate*\n\n"
                        f"💎 {title}\n"
                        f"🔢 Txns: {txns}\n"
                        f"💰 Volume(24h): ${vol:,.2f}\n"
                        f"🌊 Liquidity: ${liq:,.2f}\n"
                        f"👥 Holders: {holders}\n"
                        f"⏱ Age (min): {age_min:.1f}\n"
                        f"🏷 Score: {score:.1f}/100\n"
                        f"🔗 https://pump.fun/?view=table&coins_sort=created_timestamp"
                    )
                    # send to Telegram (async)
                    try:
                        await client.send_message(CHANNEL, msg)
                        print(f"✅ Posted candidate {title} score={score:.1f}")
                        posted.add(pool_id)
                    except Exception as e:
                        print("⚠️ Telegram send error:", e)
            # housekeeping: decay posted set over time (optional)
            # keep posted only recent ones (not implemented here - simple forever)
        except Exception as e:
            print("⚠️ monitor loop error:", e)
        await asyncio.sleep(POLL_DELAY)

# ---------------------------
# Flask keepalive
# ---------------------------
@app.route("/health")
def health():
    return "ok"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    # run flask in a thread; small risk: development server warning — fine for keep-alive
    app.run(host="0.0.0.0", port=port)

# ---------------------------
# Entrypoint (safe asyncio loop + flask thread)
# ---------------------------
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(client.start(bot_token=BOT_TOKEN))
    print("🤖 Telegram bot started")
    loop.create_task(monitor_loop())
    try:
        loop.run_forever()
    finally:
        try:
            loop.run_until_complete(client.disconnect())
        except Exception:
            pass
        loop.close()

if __name__ == "__main__":
    # launch flask keepalive
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    time.sleep(1)
    # start telegram + monitor in current process (new event loop)
    start_bot()
