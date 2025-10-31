import math

# Option B: no Telethon, just a static lookup
community_channels = {
    "pepedoge": "https://t.me/pepedoge",
}

def get_community_score(coin_id):
    try:
        # For now, static dummy score
        return 50  # adjust logic if you have other APIs
    except Exception as e:
        print(f"Community score error for {coin_id}: {e}")
        return 0
