# keep_alive.py
from flask import Flask, jsonify
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    return os.environ.get("KEEP_ALIVE_MSG", "Pump.fun bot alive ✅")

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

def run():
    port = int(os.environ.get("PORT", 5000))
    # non-production dev server is fine for Render small apps
    app.run(host="0.0.0.0", port=port)

def start():
    t = Thread(target=run, daemon=True)
    t.start()
