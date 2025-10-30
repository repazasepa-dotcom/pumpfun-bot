#!/usr/bin/env python3
# main.py  — Pump.fun strict watcher + anti-honeypot + X hype (Dexscreener)
# Educational only. Not financial advice.

import os
import time
import json
import requests
import subprocess
from datetime import datetime, timedelta
from keep_alive import keep_alive

# ---------------------------
# Config (set as env variables)
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")                     # required
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")             # e.g. @PumpFunMemeCoinAlert
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))  # seconds

# Filters (strict mode)
MIN_MC = float(os.getenv("MIN_MC", "2000"))       # lower limit market cap (USD)
MAX_MC = float(os.getenv("MAX_MC", "50000"))     # upper limit market cap (USD)
MIN_VOLUME = float(os.getenv("MIN_VOLUME", "1000"))  # 24h volume threshold (USD)
MIN_HOLDERS = int(os.getenv("MIN_HOLDERS", "20"))     # min holders
X_SCORE_THRESHOLD = int(os.getenv("X_SCORE_THRESHOLD", "20"))  # Dexscreener / X hype threshold

# Solana endpoints & Pump.fun
PUMP_API = "https://frontend-api.pump.fun/coins?offset=0&limit=60"
SOLSCAN_TOKEN_HOLDERS = "https://public-api.solscan.io/token/holders?tokenAddress={}"
SOLSCAN_TOKEN_META = "https://public-api.solscan.io/token/meta?tokenAddress={}"

# Dexscreener endpoint (social/trend)
DEXSCREENER_PAIR = "https://api.dexscreener.com/latest/dex/pairs/solana/{}"  # /{mint}

# Persistence
SEEN_FILE = os.getenv("SEEN_STORE", "/tmp/seen_pump.json")
seen = set()
try:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            seen = set(json.load(f))
except Exception:
    seen = set()

# ---------------------------
# Helpers
# ---------------------------
def save_seen():
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(list(seen), f)
    except Exception as e:
        print("Failed saving seen:", e)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("Telegram API error:", r.status_code, r.text)
    except Exception as e:
        print("Telegram send error:", e)

# ---------------------------
# Fetchers
# ---------------------------
def fetch_pump_tokens():
    try:
        r = requests.get(PUMP_API, timeout=10)
        if r.status_code == 200:
            return r.json().get("coins", []) or []
    except Exception as e:
        print("Pump.fun fetch error:", e)
    return []

def get_solscan_meta(mint):
    try:
        r = requests.get(SOLSCAN_TOKEN_META.format(mint), timeout=10)
        if r.status_code == 200:
            return r.json()  # provider format may vary
    except Exception:
        pass
    return {}

def get_solscan_holders(mint):
    try:
        r = requests.get(SOLSCAN_TOKEN_HOLDERS.format(mint), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def get_dexscreener_score(mint):
    """
    Try Dexscreener pair endpoint to get social/twitter score (best-effort).
    """
    try:
        url = DEXSCREENER_PAIR.format(mint)
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            j = r.json()
            # 'pair' object structure varies; try common fields
            pairs = j.get("pairs") or [j.get("pair")] if j.get("pair") else j.get("pair")
            # if 'pairs' is list, try first
            candidate = None
            if isinstance(j.get("pairs"), list) and j.get("pairs"):
                candidate = j.get("pairs")[0]
            elif j.get("pair"):
                candidate = j.get("pair")
            else:
                candidate = j
            # social/twitter score often under candidate['socialScore'] or candidate['socials']['twitterScore']
            s = candidate.get("socialScore") or (candidate.get("socials") or {}).get("twitterScore") or 0
            try:
                return int(float(s))
            except:
                return 0
    except Exception:
        pass
    return 0

def count_tweets_snscrape(query, minutes=10):
    """Optional fallback using snscrape if available on the host.
       Returns number of tweets found in last `minutes` minutes.
    """
    try:
        since = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:00Z")
        cmd = ['snscrape', '--jsonl', f'twitter-search "{query} since:{since}"', '--max-results', '200']
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode != 0:
            return 0
        return len([ln for ln in res.stdout.splitlines() if ln.strip()])
    except Exception:
        return 0

# ---------------------------
# Heuristics (anti-rug / anti-honeypot / dev dump)
# ---------------------------

def detect_dev_dump_by_holders(mint):
    # if top holder > 40% -> high risk
    try:
        holders = get_solscan_holders(mint)
        if isinstance(holders, list) and len(holders) > 0:
            top = holders[0]
            pct = float(top.get("percent", 0) or 0)
            if pct >= 40:
                return True, f"top_holder_pct={pct}"
    except Exception:
        pass
    return False, "no_top_holder_risk"

def detect_honeypot_by_trades(mint, pump_obj):
    """
    Best-effort honeypot detection:
    - If there are buys but no sells in recent trades -> suspect
    - If no sell liquidity or route found -> suspect
    We'll look at pump_obj trade hints and solscan holder/trades where possible.
    """
    # Check pump.fun object fields first (sometimes includes buyers/sells)
    try:
        buyers = int(pump_obj.get("token_buyers", 0) or 0)
        usd_mcap = float(pump_obj.get("usd_market_cap", 0) or 0)
    except:
        buyers = 0
        usd_mcap = 0

    # quick check: if buyers exist but pump.fun reports no sells or liquidity issues
    # pump.fun sometimes has 'complete' or liquidity flags
    if not pump_obj.get("complete", False) and usd_mcap < 10000:
        # no LP lock & small mcap -> risk
        return True, "no_lp_lock_and_low_mcap"

    # Use Solscan trades? public endpoint limited; attempt holder list as proxy
    try:
        # if holders exist but no swap txs recently, hard to be sure — we conservatively check for any sells (best-effort)
        # fallback: if zero or very low holders -> suspect honeypot
        holders = get_solscan_holders(pump_obj.get("mint"))
        if isinstance(holders, list) and len(holders) < 5:
            return True, "few_holders"
    except:
        pass

    # if nothing obvious, return no honeypot found
    return False, "no_evidence"

# ---------------------------
# Filters + decision
# ---------------------------
def passes_strict_filters(pump_obj):
    try:
        mc = float(pump_obj.get("usd_market_cap", 0) or 0)
        vol = float(pump_obj.get("usd_24h_volume", pump_obj.get("usd_volume", 0) or 0) or 0)
        holders_est = int(pump_obj.get("holders", 0) or 0)
    except:
        mc = vol = holders_est = 0

    if mc < MIN_MC or mc > MAX_MC:
        return False, "mc_out_of_range"
    if vol < MIN_VOLUME:
        return False, "low_volume"
    # Try to get holders from pump_obj or solscan fallback
    if holders_est < MIN_HOLDERS:
        # try Solscan holders count if available
        try:
            holders_list = get_solscan_holders(pump_obj.get("mint"))
            if isinstance(holders_list, list) and len(holders_list) >= MIN_HOLDERS:
                holders_est = len(holders_list)
            else:
                return False, "low_holders"
        except:
            return False, "low_holders"
    return True, "passes_filters"

# ---------------------------
# Compose analyst alert (Format B)
# ---------------------------
def format_analyst_alert(pump_obj, mc, vol, holders, x_score, risk_flags):
    name = pump_obj.get("name") or pump_obj.get("symbol") or "Unknown"
    symbol = pump_obj.get("symbol") or ""
    mint = pump_obj.get("mint") or pump_obj.get("mintAddress") or pump_obj.get("address", "")
    score_text = f"{x_score}/100"
    flags_text = ", ".join(risk_flags) if risk_flags else "None"

    message = (
        f"📊 <b>Analyst Alert</b>\n\n"
        f"<b>Token:</b> {name} {('(' + symbol + ')') if symbol else ''}\n"
        f"<b>Market Cap:</b> ${mc:,.0f}\n"
        f"<b>24h Volume:</b> ${vol:,.0f}\n"
        f"<b>Holders (est):</b> {holders}\n"
        f"<b>Social / X score:</b> {score_text}\n"
        f"<b>Risk Flags:</b> {flags_text}\n\n"
        f"🔗 Pump.fun: https://pump.fun/coin/{mint}\n"
        f"🔗 DEX Screener: https://dexscreener.com/solana/{mint}\n\n"
        f"_For research only — not financial advice._"
    )
    return message

# ---------------------------
# Main watcher loop
# ---------------------------
def run_watcher():
    print("✅ Pump.fun strict watcher (PUMP + X hype) started")
    keep_alive()  # start keep-alive server (threaded)

    while True:
        try:
            tokens = fetch_pump_tokens()
            if not tokens:
                time.sleep(POLL_INTERVAL)
                continue

            for obj in tokens:
                # The pump.fun object fields vary by endpoint; attempt to normalize
                mint = obj.get("mint") or obj.get("mintAddress") or obj.get("address")
                if not mint:
                    continue
                if mint in seen:
                    continue

                # Strict filters
                ok, reason = passes_strict_filters(obj)
                if not ok:
                    # mark seen but skip posting
                    seen.add(mint)
                    save_seen()
                    print(f"Skipped {mint} ({obj.get('name')}) reason={reason}")
                    continue

                # Honeypot check
                is_honeypot, honeypot_reason = detect_honeypot_by_trades(mint, obj)
                if is_honeypot:
                    seen.add(mint)
                    save_seen()
                    print(f"Honeypot suspected {mint}: {honeypot_reason}")
                    continue

                # Dev dump check
                dev_risk, dev_reason = detect_dev_dump_by_holders(mint)
                if dev_risk:
                    seen.add(mint)
                    save_seen()
                    print(f"Dev-dump risk {mint}: {dev_reason}")
                    continue

                # X / social score
                x_score = get_dexscreener_score(mint)
                # fallback: optionally try snscrape for name mentions (if installed)
                if x_score < X_SCORE_THRESHOLD:
                    # try snscrape quick count (best-effort)
                    name = obj.get("name") or obj.get("symbol") or mint
                    try:
                        # build a small surge score from snscrape counts
                        recent = count_tweets_snscrape(f'"{name}" OR {mint}', minutes=10)
                        prev = count_tweets_snscrape(f'"{name}" OR {mint}', minutes=30)
                        prev_only = max(0, prev - recent)
                        if recent == 0 and prev_only == 0:
                            sn_score = 0
                        elif prev_only == 0:
                            sn_score = 100
                        else:
                            ratio = recent / (prev_only or 1)
                            sn_score = min(100, int(ratio * 20))
                        if sn_score > x_score:
                            x_score = sn_score
                    except Exception:
                        pass

                # Decide: require x_score >= threshold OR pass stricter onchain filters
                if x_score >= X_SCORE_THRESHOLD:
                    # Prepare alert: gather some metrics
                    try:
                        mc = float(obj.get("usd_market_cap", obj.get("marketCap") or 0) or 0)
                        vol = float(obj.get("usd_24h_volume", obj.get("volume_24h") or 0) or 0)
                    except:
                        mc = 0
                        vol = 0

                    # Holders estimate
                    holders_est = obj.get("holders") or 0
                    if not holders_est or holders_est < MIN_HOLDERS:
                        holders_list = get_solscan_holders(mint)
                        holders_est = len(holders_list) if isinstance(holders_list, list) else holders_est

                    # risk flags (none at this point)
                    risk_flags = []

                    message = format_analyst_alert(obj, mc, vol, holders_est, x_score, risk_flags)
                    send_telegram(message)
                    print(f"Posted alert for {mint} (x_score={x_score})")
                else:
                    print(f"Not viral enough {mint} (x_score={x_score}) — skipping")

                seen.add(mint)
                save_seen()

        except Exception as e:
            print("Watcher loop error:", e)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_watcher()
