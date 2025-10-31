# Simple scoring without Telethon
import math

community_channels = {
    "pepedoge": 1000,  # Just a dummy member count
}

def get_community_score(coin_id: str):
    members = community_channels.get(coin_id, 0)
    score = min(100, int(math.log(members + 1) * 10))
    return score
