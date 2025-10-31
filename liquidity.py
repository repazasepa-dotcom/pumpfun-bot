import requests

CHAIN_ID_BSC = 56

def check_liquidity(lp_contract, lock_address):
    try:
        if not lp_contract or not lock_address:
            return False
        url = f"https://api.bscscan.com/api"
        params = {
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": lp_contract,
            "address": lock_address,
            "apikey": "YOUR_BSCSCAN_API_KEY"  # Replace with your BSC/Etherscan key
        }
        resp = requests.get(url, params=params, timeout=10).json()
        balance = int(resp.get("result", 0))
        return balance > 0
    except Exception as e:
        print("Liquidity check error:", e)
        return False
