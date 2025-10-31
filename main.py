import os
import asyncio
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telethon import TelegramClient
from community import get_community_score
from liquidity import check_liquidity
from keep_alive import run_flask

# ---------------- ENV ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
ETHERSCAN_V2_KEY = os.getenv("ETHERSCAN_V2_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@PumpFunMemeCoinAlert")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", "300"))

# ---------------- DATA ----------------
watchlist = {}
last_presales = []
previous_prices = {}
client_global = None  # will hold TelegramClient instance

# ---------------- ALERTS ----------------
# Define async functions for presale and price alerts here
# (reuse your existing logic, calling get_community_score and check_liquidity)
# Example:
async def send_presale_alerts(bot, client):
    pass

async def price_alert_task(bot):
    pass

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot is running!")

# ---------------- MAIN ----------------
async def main():
    global client_global
    t = threading.Thread(target=run_flask)
    t.start()

    client_global = TelegramClient("anon", API_ID, API_HASH)
    await client_global.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    # schedule your alerts
    from asyncio import create_task
    # app.job_queue.run_repeating(lambda ctx:create_task(send_presale_alerts(app.bot, client_global)), interval=CHECK_INTERVAL)
    # app.job_queue.run_repeating(lambda ctx:create_task(price_alert_task(app.bot)), interval=PRICE_CHECK_INTERVAL)

    print("🤖 Bot running Python 3.13 + Telethon 1.30+")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
