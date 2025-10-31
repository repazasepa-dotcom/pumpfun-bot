import requests
import os

ETHERSCAN_V2_KEY = os.environ.get("ETHERSCAN_V2_KEY")
CHAIN_ID_BSC = 56

def check_liquidity(lp_contract, lock_address):
    try:
        if not lp_contract or not lock_address:
            return False
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
