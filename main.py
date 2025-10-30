import os
import time
import requests
from flask import Flask
import threading

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT")
CHECK = int(os.getenv("POLL_INTERVAL", 20))
LOWCAP = int(os.getenv("LOWCAP_THRESHOLD_MC", 5000))

API_PUMP = "https://api.pump.fun/coins"
API_TREND = "https://api.dexscreener.com/latest/dex/tokens/solana"

sent = set()

def get_pump_new():
    try:
        data = requests.get(API_PUMP, timeout=10).json()
        return data.get("coins", [])
    except:
        return []

def trending_score(mint):
    try:
        r = requests.get(f"{API_TREND}/{mint}", timeout=10).json()
        d = r.get("pairs", [{}])[0]
        return d.get("socials", {}).get("twitterScore", 0)
    except:
        return 0

def notify(text):
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                 params={"chat_id": CHAT, "text": text, "parse_mode": "HTML"})

def run():
    notify("⚡ Pump.fun + X-trend tracker started")
    
    while True:
        coins = get_pump_new()
        for c in coins:
            mint = c.get("mint")
            if not mint or mint in sent: 
                continue

            mc = c.get("market_cap", 0)
            score = trending_score(mint)

            if mc < LOWCAP and score > 2:  # boosts detection
                text = f"""
🔥 <b>Potential Viral Meme</b>

🌱 <b>Token:</b> {c.get('name')}  
💰 <b>Market Cap:</b> {mc}
🐦 <b>Twitter Hype Score:</b> {score}
🔗 Mint: <code>{mint}</code>
🚀 pump.fun: https://pump.fun/{mint}
                """
                notify(text)
                sent.add(mint)

        time.sleep(CHECK)

# ✅ Flask keep-alive
app = Flask(__name__)
@app.route("/") 
def home(): return "Pump fun watcher alive ✅"
def keep_alive(): threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True).start()

if __name__ == "__main__":
    keep_alive()
    run()
