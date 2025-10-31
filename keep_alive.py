from flask import Flask
import os

app = Flask("KeepAlive")

@app.route("/")
def home():
    return "Bot is alive!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
