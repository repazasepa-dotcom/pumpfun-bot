# pump_api.py
import requests, time

PUMP_LIST_URL = "https://api.pump.fun/lite/tokens?offset=0&limit=50"

def fetch_pump_tokens():
    try:
        r = requests.get(PUMP_LIST_URL, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []
