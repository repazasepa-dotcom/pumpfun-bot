# keep_alive.py
from flask import Flask, jsonify
import os, threading

app = Flask(__name__)

@app.route('/')
def home():
    return os.environ.get("KEEP_ALIVE_MSG", "✅ Pump.fun watcher is running")

@app.route('/health')
def health():
    return jsonify({"status":"ok"}), 200

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def start():
    threading.Thread(target=run_web, daemon=True).start()
