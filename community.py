import math

community_channels = {
    "pepedoge": "https://t.me/pepedoge",
}

def get_community_score(coin_id: str):
    try:
        # Option B: return a static/fake score
        # Replace this with any API-based score calculation if needed
        return 50 if coin_id in community_channels else 0
    except Exception as e:
        print(f"Community score error for {coin_id}: {e}")
        return 0
