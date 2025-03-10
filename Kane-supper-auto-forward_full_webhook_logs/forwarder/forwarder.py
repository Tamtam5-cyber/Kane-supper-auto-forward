
from telethon import TelegramClient, events
from telethon.errors import RPCError
from config import API_ID, API_HASH, SESSION_NAME, SOURCE_CHAT_IDS, TARGET_CHAT_IDS, ENABLE_FORWARD, ADMIN_TELEGRAM_ID
from forwarder.utils import should_forward
import logging
import requests

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

logging.basicConfig(filename='logs/forward.log', level=logging.INFO)

async def safe_forward(client, target, message):
    try:
        await client.send_message(target, message)
        logging.info(f"[FORWARD] {message.chat_id} → {target} : {message.text[:50] if message.text else 'media/sticker'}")
    except RPCError as e:
        await client.send_message(ADMIN_TELEGRAM_ID, f"❌ Lỗi gửi đến {target}:
{str(e)}")

@client.on(events.NewMessage(chats=SOURCE_CHAT_IDS))
async def handler(event):
    if not ENABLE_FORWARD():
        return
    if should_forward(event.message):
        for target in TARGET_CHAT_IDS:
            await safe_forward(client, target, event.message)

# Command từ Admin /bật /tắt
@client.on(events.NewMessage(pattern='/bật|/tắt'))
async def cmd_handler(event):
    sender = await event.get_sender()
    sender_id = sender.id
    message = event.raw_text

    if sender_id != ADMIN_TELEGRAM_ID:
        return

    requests.post("http://localhost:5000/webhook", json={
        "sender_id": sender_id,
        "message": message
    })

    await event.reply(f"✅ Đã gửi lệnh: {message}")

client.start()
client.run_until_disconnected()
