from telethon import TelegramClient, events
import json
import asyncio
import config
import datetime

client = TelegramClient("session", config.API_ID, config.API_HASH)

# Load danh sách từ khóa & danh sách nguồn hợp lệ
with open("filters.json") as f:
    FILTER_KEYWORDS = json.load(f)["keywords"]

with open("allowlist.json") as f:
    ALLOWLIST = json.load(f)

SOURCE_CHAT_IDS = (
    ALLOWLIST["allowed_groups"] +
    ALLOWLIST["allowed_channels"] +
    ALLOWLIST["allowed_users"]
)
TARGET_CHAT_IDS = [-100222333444]  # ID nhóm/kênh đích

def log_message(message):
    with open(config.LOG_FILE, "a") as log_file:
        log_file.write(f"{datetime.datetime.now()} - {message}
")

@client.on(events.NewMessage(chats=SOURCE_CHAT_IDS))
async def forward_message(event):
    if not config.BOT_STATUS["running"]:
        return
    
    text = event.message.text or ""
    if any(keyword.lower() in text.lower() for keyword in FILTER_KEYWORDS):
        for chat_id in TARGET_CHAT_IDS:
            await asyncio.sleep(config.DELAY)
            await client.send_message(chat_id, event.message)
            log_message(f"Forwarded message to {chat_id}: {text[:50]}...")

print("Bot forward đang chạy...")
client.start()
client.run_until_disconnected()
