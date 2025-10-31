import requests
import os

BSC_API_KEY = os.getenv("BSC_API_KEY")

def check_liquidity(lp_contract, lock_address):
    try:
        url = f"https://api.bscscan.com/api?module=account&action=tokenbalance&contractaddress={lp_contract}&address={lock_address}&apikey={BSC_API_KEY}"
        data = requests.get(url, timeout=10).json()
        balance = int(data['result'])
        return balance > 0
    except Exception as e:
        print("Liquidity check error:", e)
        return False
