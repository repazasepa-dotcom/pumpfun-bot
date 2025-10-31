# Mock community scoring without Telethon
def get_community_score(coin_id):
    # You can replace this with real API-based scoring if available
    community_data = {
        "pepedoge": 70,
        "sachicoin": 45,
    }
    return community_data.get(coin_id, 0)
