from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run():
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
