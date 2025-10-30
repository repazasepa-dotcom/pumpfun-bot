from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "PumpFun Bot Alive ✅"

def run():
    app.run(host="0.0.0.0", port=5000)

def keep_alive():
    Thread(target=run).start()
