import requests
import os

ETHERSCAN_V2_KEY = os.getenv("ETHERSCAN_V2_KEY")
CHAIN_ID_BSC = 56  # Binance Smart Chain

def check_liquidity(lp_contract, lock_address):
    try:
        url = "https://api.etherscan.io/v2/api"
        params = {
            "chainid": CHAIN_ID_BSC,
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": lp_contract,
            "address": lock_address,
            "apikey": ETHERSCAN_V2_KEY
        }
        resp = requests.get(url, params=params, timeout=10).json()
        balance = int(resp.get("data", {}).get("result", 0))
        return balance > 0
    except Exception as e:
        print("Liquidity check error:", e)
        return False
