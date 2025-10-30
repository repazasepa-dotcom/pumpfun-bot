# main.py
import os, time, threading
from keep_alive import start as start_web
from pump_api import fetch_pump_tokens
from birdeye_api import token_info, trades
from x_hype import compute_score
from heuristics import detect_dev_dump, detect_honeypot, check_liquidity_locked
from alerts import send_message_md, format_alert
from telethon import TelegramClient
from admin_handlers import register_admin

# Config from env
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL = os.getenv("TELEGRAM_CHAT", "@PumpFunMemeCoinAlert")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
VIP_CHANNEL = os.getenv("VIP_CHANNEL", "")  # optional VIP channel
LOWCAP_THRESHOLD_MC = float(os.getenv("LOWCAP_THRESHOLD_MC", "5000"))  # $value

# Telethon for admin tasks (not required for posting; uses alerts.send_message_md for posting)
client = TelegramClient("pump_main", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
seen = set()

def evaluate_token(t):
    addr = t.get("mint")
    metrics = token_info(addr) or {}
    heur_dev = detect_dev_dump(addr, metrics)
    heur_honey = detect_honeypot(addr, metrics)
    liq_locked = check_liquidity_locked(t) or metrics.get("liquidity_locked", False)
    x = compute_score(metrics.get("name") or t.get("name", ""), addr)
    return metrics, heur_dev, heur_honey, liq_locked, x

def watcher_loop():
    print("Main watcher started.")
    while True:
        try:
            tokens = fetch_pump_tokens()
            for t in tokens:
                addr = t.get("mint")
                if not addr or addr in seen:
                    continue
                seen.add(addr)
                metrics, dev, honey, locked, x = evaluate_token(t)
                lowcap = (t.get("usd_market_cap", 0) <= LOWCAP_THRESHOLD_MC)
                msg = format_alert(t, metrics or {}, {"dump": dev.get("dump",False), "honeypot": honey.get("honeypot", False), "liquidity_locked": locked}, x.get("score"), vip=False, lowcap=lowcap)
                # decision logic:
                if x.get("score",0) >= 30 and not honey.get("honeypot"):
                    send_message_md(msg)
                elif not dev.get("dump") and not honey.get("honeypot") and locked:
                    send_message_md(msg)
                # VIP: if VIP_CHANNEL set and high score, post also to VIP
                if VIP_CHANNEL and x.get("score",0) >= 60:
                    # post to vip channel by overriding TELEGRAM_CHAT env temporarily
                    prev = os.getenv("TELEGRAM_CHAT")
                    os.environ["TELEGRAM_CHAT"] = VIP_CHANNEL
                    send_message_md(msg)
                    if prev is not None:
                        os.environ["TELEGRAM_CHAT"] = prev
                time.sleep(1)
        except Exception as e:
            print("Watcher error:", e)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    # start web for keepalive
    start_web()

    # register admin handlers (non-blocking)
    if ADMIN_ID:
        register_admin(client, ADMIN_ID, seen, None)

    # start watcher thread
    threading.Thread(target=watcher_loop, daemon=True).start()

    # keep main thread alive, also start Telethon loop
    client.run_until_disconnected()
