from flask import Flask
import threading

app = Flask("keep_alive")

@app.route("/")
def home():
    return "PumpFun Bot is alive ✅"

def run():
    app.run(host="0.0.0.0", port=5000)

def keep_alive():
    # Run Flask app in a separate thread
    t = threading.Thread(target=run)
    t.start()
