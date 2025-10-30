import os, time, asyncio, requests
from keep_alive import start
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT")
LOWCAP_THRESHOLD = int(os.getenv("LOWCAP_THRESHOLD_MC", 5000))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 20))

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

API_URL = "https://pump.fun/api/trending"

last_scanned = set()

async def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, json=data)
    except:
        pass

async def scan_pumpfun():
    global last_scanned
    try:
        r = requests.get(API_URL, timeout=10).json()
        tokens = r.get("tokens", [])

        for t in tokens:
            addr = t.get("mint")
            mc = t.get("usd_market_cap", 0)

            # Skip if already processed
            if addr in last_scanned:
                continue

            last_scanned.add(addr)

            if mc < LOWCAP_THRESHOLD:
                msg = f"""
🚀 <b>New Pump.fun Launch</b>
🎯 <b>{t.get('name')}</b>
💰 MC: ${mc:,}
🪙 Token: <code>{addr}</code>
🌍 https://pump.fun/coin/{addr}
                """
                await send_telegram(msg)
                print(f"[PUMP-ALERT] {t.get('name')} ${mc}")

    except Exception as e:
        print("ERROR scanning pump.fun:", e)

async def monitor_pumpfun():
    print("✅ Pump.fun watcher loop running...")
    while True:
        await scan_pumpfun()
        await asyncio.sleep(POLL_INTERVAL)

# ✅ /forcecheck debug command
from flask import request
from keep_alive import app

@app.route("/forcecheck")
def forcecheck():
    asyncio.create_task(scan_pumpfun())
    return "Manual scan triggered ✅"

# ✅ Startup sequence
if __name__ == "__main__":
    start()  # start Flask keep alive

    async def runner():
        asyncio.create_task(monitor_pumpfun())

        print("✅ Pump.fun bot fully running")
        while True:
            await asyncio.sleep(10)

    asyncio.run(runner())
