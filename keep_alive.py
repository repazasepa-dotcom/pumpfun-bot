from flask import Flask

app = Flask("KeepAlive")

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)
