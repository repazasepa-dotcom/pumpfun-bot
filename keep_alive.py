from flask import Flask
import os

PORT = int(os.getenv("PORT", "10000"))
app_flask = Flask("KeepAlive")

@app_flask.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)
