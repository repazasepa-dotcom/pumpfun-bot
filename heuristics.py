# heuristics.py
from birdeye_api import token_info, trades
import requests

def check_liquidity_locked(token_raw):
    # check if pump.fun object or birdeye shows liquidity locked / "complete" boolean
    if isinstance(token_raw, dict):
        return token_raw.get("complete") or token_raw.get("liquidity_locked") or False
    return False

def detect_dev_dump(address, metrics_raw):
    # metrics_raw may come from birdeye token_info
    be = metrics_raw or token_info(address)
    if not be:
        return {"dump": False, "reason": "no_data"}
    # quick heuristic: top holder > 40%
    holders = be.get("holders") or be.get("holder_count") or []
    # birdeye `holders` may be list of dicts with percent
    try:
        top = None
        if isinstance(holders, list) and holders:
            top = max(holders, key=lambda x: float(x.get("percent",0) or 0))
        if top:
            pct = float(top.get("percent", 0) or 0)
            if pct >= 40:
                return {"dump": True, "reason": f"top_holder_pct={pct}"}
    except Exception:
        pass
    # check recent trades for creator outbound movement
    txs = be.get("txs") or be.get("trades") or []
    moved_from_creator = 0
    for tx in txs[:120]:
        fr = tx.get("from")
        amt = float(tx.get("amount", 0) or 0)
        # if fr==creator etc - heuristics omitted for brevity
        if fr and amt>0:
            moved_from_creator += amt
            if moved_from_creator>0:
                return {"dump": True, "reason":"creator_moved_funds"}
    return {"dump": False, "reason": "no_evidence"}

def detect_honeypot(address, metrics_raw):
    be = metrics_raw or token_info(address)
    if not be:
        return {"honeypot": False, "reason":"no_data"}
    txs = be.get("trades") or be.get("txs") or []
    buys = sum(1 for t in txs if str(t.get("side","")).lower()=="buy")
    sells = sum(1 for t in txs if str(t.get("side","")).lower()=="sell")
    if buys>0 and sells==0:
        return {"honeypot": True, "reason":"buys_no_sells"}
    # failed sells
    failed_sells = sum(1 for t in txs if t.get("status") and "fail" in t.get("status","").lower())
    if failed_sells>0 and failed_sells/(sells or 1) > 0.5:
        return {"honeypot": True, "reason":"many_failed_sells"}
    return {"honeypot": False, "reason":"none"}
