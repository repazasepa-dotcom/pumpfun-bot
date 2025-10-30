# alerts.py
import os, requests, json
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT")
TG_SEND = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

def send_message_md(text):
    payload = {"chat_id": CHAT, "text": text, "parse_mode":"Markdown", "disable_web_page_preview": False}
    try:
        r = requests.post(TG_SEND, json=payload, timeout=12)
        return r.status_code==200
    except Exception:
        return False

def format_alert(token, metrics, heur, xscore, vip=False, lowcap=False):
    name = metrics.get("name") or token.get("name")
    sym = metrics.get("symbol") or token.get("symbol","")
    addr = token.get("mint") or token.get("mintAddress") or token.get("mint_id")
    buyers = token.get("token_buyers") or metrics.get("buyers") or 0
    vol = token.get("usd_market_cap") or metrics.get("volume_24h_sol") or 0
    locked = heur.get("liquidity_locked") if heur.get("liquidity_locked") is not None else token.get("complete", False)

    flags=[]
    if heur.get("dump", False): flags.append("🚨 DevDumpRisk")
    if heur.get("honeypot", False): flags.append("🚨 Honeypot")
    if lowcap: flags.append("⚠️ LowCap")
    if vip: flags.append("⭐ VIP")

    txt = (
        f"🆕 *Pump.fun Candidate*\n\n"
        f"*{name}* ({sym})\n"
        f"`{addr}`\n\n"
        f"Buyers: *{buyers}*  Vol/MC est: *{vol}*\n"
        f"LP Locked: *{locked}*\n\n"
        f"*Flags:* {' '.join(flags) if flags else 'None'}\n"
        f"*X buzz score:* {xscore}\n\n"
        f"🔗 https://pump.fun/{addr}\n"
        f"🔗 https://dexscreener.com/solana/{addr}\n\n"
        f"_For research only, not financial advice._\n"
        f"_Detected at {datetime.now(timezone.utc).isoformat()} UTC_"
    )
    return txt
