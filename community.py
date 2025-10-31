import math
import requests

async def get_community_score(coin_id: str):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id.lower()}"
        resp = requests.get(url, timeout=10).json()
        data = resp.get("community_data", {})
        twitter = data.get("twitter_followers", 0) or 0
        reddit = data.get("reddit_subscribers", 0) or 0
        score = min(100, int((twitter + reddit + 1)**0.1 * 10))  # logarithmic-like scaling
        return score
    except Exception as e:
        print(f"Community score error for {coin_id}: {e}")
        return 0
