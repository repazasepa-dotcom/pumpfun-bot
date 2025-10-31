import os
import asyncio
import requests
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from keep_alive import run_flask
from liquidity import check_liquidity

# ---------------- ENV VARIABLES ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ETHERSCAN_V2_KEY = os.getenv("ETHERSCAN_V2_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@PumpFunMemeCoinAlert")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", "300"))

# ---------------- DATA ----------------
watchlist = {}
last_presales = []
previous_prices = {}

# ---------------- COMMUNITY SCORE (CoinGecko) ----------------
async def get_community_score(coin_id: str):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id.lower()}"
        resp = requests.get(url, timeout=10).json()
        data = resp.get("community_data", {})
        twitter = data.get("twitter_followers", 0) or 0
        reddit = data.get("reddit_subscribers", 0) or 0
        score = min(100, int((twitter + reddit + 1)**0.1 * 10))  # logarithmic-like scaling
        return score
    except Exception as e:
        print(f"Community score error for {coin_id}: {e}")
        return 0

# ---------------- PRESALES ----------------
def get_presales():
    presales = []
    try:
        url = "https://api.pinksale.finance/api/v1/presales"
        data = requests.get(url, timeout=10).json()
        for item in data:
            presale_id = item['id']
            if not any(p['id']==presale_id for p in last_presales):
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

# ---------------- ALERTS ----------------
async def send_presale_alerts(bot):
    presales = get_presales()
    for p in presales:
        liquidity = check_liquidity(p['lp_contract'], p['lock_address'])
        score = await get_community_score(p['coin_id'])
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
                change = ((price-old)/old)*100
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

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 MemeCoin Scout Bot\n"
        "/newcoins\n/watchlist_add <coin_id>\n/watchlist_remove <coin_id>\n/watchlist_show\n/info <coin_id>"
    )

async def watchlist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /watchlist_add <coin_id>")
        return
    coin = context.args[0].lower()
    watchlist.setdefault(user, set()).add(coin)
    await update.message.reply_text(f"✅ {coin} added.")

async def watchlist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /watchlist_remove <coin_id>")
        return
    coin = context.args[0].lower()
    if user in watchlist and coin in watchlist[user]:
        watchlist[user].remove(coin)
        await update.message.reply_text(f"❌ {coin} removed.")
    else:
        await update.message.reply_text(f"{coin} not in watchlist.")

async def watchlist_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    coins = watchlist.get(user, set())
    await update.message.reply_text("\n".join(coins) if coins else "Your watchlist is empty.")

async def newcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    presales = get_presales()
    if not presales:
        await update.message.reply_text("No new presales.")
        return
    msg = "🆕 Latest Presales:\n" + "\n".join([f"{p['name']} ({p['coin_id']}) - {p['url']}" for p in presales[:5]])
    await update.message.reply_text(msg)

async def token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /info <coin_id>")
        return
    coin = context.args[0].lower()
    score = await get_community_score(coin)
    await update.message.reply_text(f"ℹ️ {coin} Community Score: {score}/100")

# ---------------- MAIN ----------------
async def main():
    # Start Flask keep-alive
    t = threading.Thread(target=run_flask)
    t.start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("watchlist_add", watchlist_add))
    app.add_handler(CommandHandler("watchlist_remove", watchlist_remove))
    app.add_handler(CommandHandler("watchlist_show", watchlist_show))
    app.add_handler(CommandHandler("newcoins", newcoins))
    app.add_handler(CommandHandler("info", token_info))

    # Schedule tasks
    from asyncio import create_task
    app.job_queue.run_repeating(lambda ctx: create_task(send_presale_alerts(app.bot)), interval=CHECK_INTERVAL, first=10)
    app.job_queue.run_repeating(lambda ctx: create_task(price_alert_task(app.bot)), interval=PRICE_CHECK_INTERVAL, first=15)

    print("🤖 Bot running without Telethon, using CoinGecko social scores.")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
