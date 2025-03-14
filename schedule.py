from telethon import TelegramClient
import asyncio
import config
import datetime

client = TelegramClient("scheduler_session", config.API_ID, config.API_HASH)

# Danh sách tin nhắn lên lịch
SCHEDULED_MESSAGES = [
    {"chat_id": -1001122334455, "text": "🌟 Tin nhắn tự động mỗi ngày!", "time": "08:00", "interval": 30},
    {"chat_id": -1009988776655, "text": "🚀 Đừng quên tham gia event hôm nay!", "time": "12:00", "interval": 60}
]

async def send_scheduled_messages():
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        for msg in SCHEDULED_MESSAGES:
            if now == msg["time"]:
                await client.send_message(msg["chat_id"], msg["text"])
                print(f"✅ Gửi tin nhắn đến {msg['chat_id']} lúc {now}")

        await asyncio.sleep(60)  # Kiểm tra mỗi phút

async def main():
    await client.start()
    print("📅 Bot gửi tin nhắn tự động đang chạy...")
    await send_scheduled_messages()

with client:
    client.loop.run_until_complete(main())
