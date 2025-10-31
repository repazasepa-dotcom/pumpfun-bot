# meme_coin_scout_bot_full.py
import os
import asyncio
import requests
import math
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetFullChannel
from flask import Flask
import threading

# ---------------- ENVIRONMENT VARIABLES ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BSC_API_KEY = os.getenv("BSC_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@PumpFunMemeCoinAlert")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # presale alert interval in sec
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", "300"))  # price check interval in sec

# ---------------- DATA STORAGE ----------------
watchlist = {}
last_presales = []  # list of dicts with coin info
previous_prices = {}  # token_address: last_price

community_channels = {
    "pepedoge": "https://t.me/pepedoge",
}

# ---------------- FLASK KEEP ALIVE ----------------
app_flask = Flask("KeepAlive")

@app_flask.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# ---------------- HELPER FUNCTIONS ----------------
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
        print("Error fetching presales:", e)
    return presales

def check_liquidity(lp_contract, lock_address):
    try:
        url = f"https://api.bscscan.com/api?module=account&action=tokenbalance&contractaddress={lp_contract}&address={lock_address}&apikey={BSC_API_KEY}"
        data = requests.get(url, timeout=10).json()
        balance = int(data['result'])
        return balance > 0
    except Exception as e:
        print("Liquidity check error:", e)
        return False

def get_community_score(client, coin_id):
    try:
        channel_link = community_channels.get(coin_id)
        if not channel_link:
            return 0
        channel_entity = client.get_entity(channel_link)
        full = client(GetFullChannel(channel=channel_entity))
        member_count = full.full_chat.participants_count
        score = min(100, int(math.log(member_count + 1) * 10))
        return score
    except Exception as e:
        print(f"Community score error for {coin_id}: {e}")
        return 0

# ---------------- ALERT FUNCTIONS ----------------
async def send_presale_alerts(bot, client):
    presales = get_presales()
    if not presales:
        return
    for presale in presales:
        liquidity_locked = check_liquidity(presale['lp_contract'], presale['lock_address'])
        community_score = get_community_score(client, presale['coin_id'])
        msg = (
            f"🚀 *New Meme Coin Presale!*\n\n"
            f"*Name:* {presale['name']}\n"
            f"*Status:* {presale['status']}\n"
            f"*Contract:* [`{presale['token_contract']}`](https://bscscan.com/token/{presale['token_contract']})\n"
            f"*Liquidity Locked:* {'✅' if liquidity_locked else '❌'}\n"
            f"*Community Score:* {community_score}/100\n"
            f"*Website:* [Link]({presale['url']})\n"
        )
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending presale alert: {e}")

async def price_alert_task(bot):
    COINGECKO_API = "https://api.coingecko.com/api/v3/simple/token_price/binance-smart-chain"
    while True:
        for presale in last_presales:
            try:
                token_address = presale['token_contract']
                params = {"contract_addresses": token_address, "vs_currencies": "usd"}
                response = requests.get(COINGECKO_API, params=params, timeout=10).json()
                price = response.get(token_address.lower(), {}).get("usd")
                if price is None:
                    continue
                old_price = previous_prices.get(token_address)
                if old_price is None:
                    previous_prices[token_address] = price
                    continue
                change = ((price - old_price) / old_price) * 100
                if abs(change) >= 10:  # 10% threshold
                    msg = (
                        f"📈 *Price Alert!* {presale['name']} ({presale['coin_id']})\n"
                        f"Price: ${price:.6f} ({change:+.2f}%)\n"
                        f"[Contract](https://bscscan.com/token/{token_address})"
                    )
                    await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
                    previous_prices[token_address] = price
            except Exception as e:
                print(f"Price alert error: {e}")
        await asyncio.sleep(PRICE_CHECK_INTERVAL)

# ---------------- COMMAND HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 MemeCoin Scout Bot\n"
        "Commands:\n"
        "/newcoins - Show latest presales\n"
        "/watchlist_add <coin_id>\n"
        "/watchlist_remove <coin_id>\n"
        "/watchlist_show\n"
        "/info <coin_id>"
    )

async def watchlist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /watchlist_add <coin_id>")
        return
    coin = context.args[0].lower()
    watchlist.setdefault(user_id, set()).add(coin)
    await update.message.reply_text(f"✅ {coin} added to your watchlist.")

async def watchlist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /watchlist_remove <coin_id>")
        return
    coin = context.args[0].lower()
    if user_id in watchlist and coin in watchlist[user_id]:
        watchlist[user_id].remove(coin)
        await update.message.reply_text(f"❌ {coin} removed from watchlist.")
    else:
        await update.message.reply_text(f"{coin} not in your watchlist.")

async def watchlist_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    coins = watchlist.get(user_id, set())
    msg = "\n".join(coins) if coins else "Your watchlist is empty."
    await update.message.reply_text(msg)

async def newcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    presales = get_presales()
    if not presales:
        await update.message.reply_text("No new presales found.")
        return
    msg = "🆕 Latest Presales:\n"
    for p in presales[:5]:
        msg += f"{p['name']} ({p['coin_id']}) - {p['url']}\n"
    await update.message.reply_text(msg)

async def token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /info <coin_id>")
        return
    coin_id = context.args[0].lower()
    client = TelegramClient("anon_session", API_ID, API_HASH)
    await client.start()
    community_score = get_community_score(client, coin_id)
    await update.message.reply_text(f"ℹ️ Info for {coin_id}:\nCommunity Score: {community_score}/100")

# ---------------- MAIN ----------------
async def main():
    t = threading.Thread(target=run_flask)
    t.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("watchlist_add", watchlist_add))
    app.add_handler(CommandHandler("watchlist_remove", watchlist_remove))
    app.add_handler(CommandHandler("watchlist_show", watchlist_show))
    app.add_handler(CommandHandler("newcoins", newcoins))
    app.add_handler(CommandHandler("info", token_info))

    # Background tasks
    from asyncio import create_task
    app.job_queue.run_repeating(lambda ctx: create_task(presale_alert_task(app)), interval=CHECK_INTERVAL, first=10)
    app.job_queue.run_repeating(lambda ctx: create_task(price_alert_task(app.bot)), interval=PRICE_CHECK_INTERVAL, first=15)

    print("🤖 MemeCoin Scout Bot is running with presale & price alerts, keep-alive enabled.")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
