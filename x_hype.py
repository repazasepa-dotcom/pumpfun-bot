# x_hype.py
import subprocess, shlex
from datetime import datetime, timedelta

def _count_mentions(query, minutes=10):
    # counts tweets with snscrape for last `minutes`
    since = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:00Z")
    # build snscrape query
    q = f'{query} since:{since}'
    cmd = f'snscrape --jsonl "twitter-search \\"{q}\\"" --max-results 200'
    try:
        proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            return 0
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        return len(lines)
    except Exception:
        return 0

def compute_score(name, mint):
    q = f'"{name}" OR {mint} OR "pump.fun/{mint}"'
    recent = _count_mentions(q, minutes=10)
    prev = _count_mentions(q, minutes=30)  # last 30 includes recent; this is rough
    prev_only = max(0, prev - recent)
    if recent == 0 and prev_only == 0:
        return {"recent":0,"prev":0,"score":0}
    if prev_only == 0:
        score = 100
    else:
        ratio = recent / (prev_only or 1)
        score = min(100, int(ratio * 20))
    return {"recent": recent, "previous": prev_only, "score": score}
