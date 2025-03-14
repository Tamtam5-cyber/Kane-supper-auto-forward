from telethon import TelegramClient, events, Button
import json
import config

bot = TelegramClient("bot_session", config.API_ID, config.API_HASH).start(bot_token=config.BOT_TOKEN)

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    if event.sender_id in config.ADMIN_IDS:
        buttons = [
            [Button.inline("🟢 Bật Forward", b"forward_on"), Button.inline("🔴 Tắt Forward", b"forward_off")],
            [Button.inline("📜 Xem từ khóa", b"list_keywords"), Button.inline("➕ Thêm từ khóa", b"add_keyword")],
            [Button.inline("📡 Xem nguồn", b"list_sources"), Button.inline("➕ Thêm nguồn", b"add_source")],
            [Button.inline("📊 Trạng thái bot", b"status")]
        ]
        await event.respond("🎯 **Quản lý bot forwarding**", buttons=buttons)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode("utf-8")

    if data == "forward_on":
        config.BOT_STATUS["running"] = True
        await event.edit("✅ Forwarding **Đã bật**")
    elif data == "forward_off":
        config.BOT_STATUS["running"] = False
        await event.edit("⛔ Forwarding **Đã tắt**")
    elif data == "status":
        status = "🟢 Đang chạy" if config.BOT_STATUS["running"] else "🔴 Đã tắt"
        await event.edit(f"⚙️ Trạng thái bot: {status}")
    elif data == "list_keywords":
        with open("filters.json") as f:
            keywords = json.load(f)["keywords"]
        await event.edit("📜 **Danh sách từ khóa:**
" + "\n".join(keywords))
    elif data == "list_sources":
        with open("allowlist.json") as f:
            sources = json.load(f)
        await event.edit("📡 **Nguồn hợp lệ:**
" + "\n".join(map(str, sources["allowed_groups"])))
    else:
        await event.answer("⚡ Chức năng đang cập nhật!", alert=True)

print("Bot điều khiển đang chạy...")
bot.run_until_disconnected()
