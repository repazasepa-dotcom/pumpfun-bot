# admin_handlers.py
from telethon import events, Button
from telethon.tl.types import PeerChannel
import json, os

CONFIG_FILE = "forward_config.json"  # or your own admin store

def register_admin(client, admin_id, seen_set, config):
    @client.on(events.NewMessage(pattern="/admin"))
    async def admin_menu(event):
        if event.sender_id != admin_id:
            await event.respond("Unauthorized.")
            return
        buttons = [
            [Button.inline("🔧 Set thresholds", b"set_thresh")],
            [Button.inline("📤 Send test", b"test_send")],
            [Button.inline("📋 View seen", b"view_seen")],
            [Button.inline("⭐ Toggle VIP mode", b"toggle_vip")],
        ]
        await event.respond("Admin panel:", buttons=buttons)

    @client.on(events.CallbackQuery)
    async def cb(event):
        data = event.data.decode()
        if event.sender_id != admin_id:
            await event.answer("Not allowed", alert=True)
            return
        if data=="view_seen":
            text = "Seen tokens:\n" + "\n".join(list(seen_set)[:200])
            await event.respond(text[:4000])
        if data=="test_send":
            await client.send_message(admin_id, "Test message from bot.")
