import math
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetFullChannel

community_channels = {
    "pepedoge": "https://t.me/pepedoge",
}

def get_community_score(client: TelegramClient, coin_id: str):
    try:
        channel_link = community_channels.get(coin_id)
        if not channel_link:
            return 0
        channel_entity = client.get_entity(channel_link)
        full = client(GetFullChannel(channel=channel_entity))
        member_count = full.full_chat.participants_count
        score = min(100, int(math.log(member_count + 1) * 10))
        return score
    except Exception as e:
        print(f"Community score error for {coin_id}: {e}")
        return 0
