from __future__ import annotations

import os
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot ishlayapti!"

def run() -> None:
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

def keep_alive() -> None:
    thread = Thread(target=run, daemon=True)
    thread.start()