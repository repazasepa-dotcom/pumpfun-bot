from flask import Flask
import os

PORT = int(os.getenv("PORT", "10000"))
app = Flask("KeepAlive")

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)
