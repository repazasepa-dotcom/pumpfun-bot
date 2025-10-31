import os
import asyncio
import requests
import threading
from telegram.ext import ApplicationBuilder, CommandHandler
from keep_alive import run_flask
from liquidity import check_liquidity
from community import get_community_score

# ENV VARIABLES
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@PumpFunMemeCoinAlert")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", "300"))

last_presales = []
previous_prices = {}

# PRESALES
def get_presales():
    presales = []
    try:
        url = "https://api.pinksale.finance/api/v1/presales"
        data = requests.get(url, timeout=10).json()
        for item in data:
            presale_id = item['id']
            if not any(p['id'] == presale_id for p in last_presales):
                presale = {
                    "id": presale_id,
                    "name": item['name'],
                    "url": item['website'],
                    "status": item['status'],
                    "coin_id": item['token_symbol'].lower(),
                    "token_contract": item['tokenAddress'],
                    "lp_contract": item.get('lpAddress'),
                    "lock_address": item.get('lockAddress')
                }
                presales.append(presale)
                last_presales.append(presale)
    except Exception as e:
        print("Presale fetch error:", e)
    return presales

# ALERTS
async def send_presale_alerts(bot):
    presales = get_presales()
    for p in presales:
        liquidity = check_liquidity(p['lp_contract'], p['lock_address'])
        score = get_community_score(p['coin_id'])
        msg = (
            f"🚀 *New Meme Coin Presale!*\n\n"
            f"*Name:* {p['name']}\n"
            f"*Status:* {p['status']}\n"
            f"*Contract:* [`{p['token_contract']}`](https://bscscan.com/token/{p['token_contract']})\n"
            f"*Liquidity Locked:* {'✅' if liquidity else '❌'}\n"
            f"*Community Score:* {score}/100\n"
            f"*Website:* [Link]({p['url']})"
        )
        try:
            await bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
        except Exception as e:
            print("Alert send error:", e)

async def price_alert_task(bot):
    COINGECKO_API = "https://api.coingecko.com/api/v3/simple/token_price/binance-smart-chain"
    while True:
        for p in last_presales:
            try:
                token = p['token_contract']
                params = {"contract_addresses": token, "vs_currencies": "usd"}
                price = requests.get(COINGECKO_API, params=params, timeout=10).json().get(token.lower(), {}).get("usd")
                if price is None: continue
                old = previous_prices.get(token)
                if old is None:
                    previous_prices[token] = price
                    continue
                change = ((price - old) / old) * 100
                if abs(change) >= 10:
                    msg = (
                        f"📈 *Price Alert!* {p['name']} ({p['coin_id']})\n"
                        f"Price: ${price:.6f} ({change:+.2f}%)\n"
                        f"[Contract](https://bscscan.com/token/{token})"
                    )
                    await bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
                    previous_prices[token] = price
            except Exception as e:
                print("Price alert error:", e)
        await asyncio.sleep(PRICE_CHECK_INTERVAL)

# COMMANDS
async def start(update, context):
    await update.message.reply_text(
        "🚀 MemeCoin Scout Bot\n"
        "/newcoins"
    )

async def newcoins(update, context):
    presales = get_presales()
    if not presales:
        await update.message.reply_text("No new presales.")
        return
    msg = "🆕 Latest Presales:\n" + "\n".join([f"{p['name']} ({p['coin_id']}) - {p['url']}" for p in presales[:5]])
    await update.message.reply_text(msg)

# MAIN
async def main():
    threading.Thread(target=run_flask).start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newcoins", newcoins))

    app.job_queue.run_repeating(lambda ctx: asyncio.create_task(send_presale_alerts(app.bot)),
                                interval=CHECK_INTERVAL, first=10)
    app.job_queue.run_repeating(lambda ctx: asyncio.create_task(price_alert_task(app.bot)),
                                interval=PRICE_CHECK_INTERVAL, first=15)

    print("🤖 Bot running with presale & price alerts, Python-telegram-bot v20-ready.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
