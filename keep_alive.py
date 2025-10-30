# keep_alive.py
from flask import Flask, jsonify
import threading, os

app = Flask(__name__)

@app.route("/")
def home():
    return os.environ.get("KEEP_ALIVE_MSG", "✅ Pump.fun watcher running")

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run, daemon=True)
    t.start()
