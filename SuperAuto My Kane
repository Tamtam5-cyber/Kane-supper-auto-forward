import logging
import asyncio
import json
import re
import os
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import UserStatusOnline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Cấu hình logging
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Thông tin bot
BOT_TOKEN = "7695124221:AAGhrm4zaIeMwtipSPqa_44Pq4gw9ZF4668"  # Token từ BotFather
API_ID = "24090485"  # API ID từ my.telegram.org
API_HASH = "b056e6499bc0d4a81ab375773ac1170c"  # API Hash từ my.telegram.org
ADMIN_IDS = [123456789]  # Thay bằng danh sách ID của admin

# Lưu trữ dữ liệu
clients = {}  # {chat_id: client}
user_data = {}  # {chat_id: {phone, source, target, blacklist, whitelist, replace_dict, emoji_replace, forward_mode, broadcast_enabled, broadcast_target, cleaners}}
forward_rules = {}  # {chat_id: {label: {source_chat_ids, target_chat_ids}}}
whitelist = {}  # {chat_id: {label: {type, words/pattern/users}}}
allowed_users = []  # Danh sách người dùng được phép
settings = {"forward_enabled": True, "whitelist_enabled": True, "forward_mode": "forward"}  # Cài đặt mặc định
statistics = {"forwarded_messages": [], "online_users": []}  # Thống kê

# File để lưu cấu hình
WHITELIST_FILE = "whitelist.json"
FORWARD_RULES_FILE = "forward_rules.json"
USERS_FILE = "users.json"
SETTINGS_FILE = "settings.json"
STATISTICS_FILE = "statistics.json"

# Tải cấu hình từ file
def load_whitelist():
    try:
        with open(WHITELIST_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_whitelist(whitelist):
    with open(WHITELIST_FILE, 'w') as f:
        json.dump(whitelist, f, indent=4)

def load_forward_rules():
    try:
        with open(FORWARD_RULES_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_forward_rules(forward_rules):
    with open(FORWARD_RULES_FILE, 'w') as f:
        json.dump(forward_rules, f, indent=4)

def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"forward_enabled": True, "whitelist_enabled": True, "forward_mode": "forward"}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

def load_statistics():
    try:
        with open(STATISTICS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"forwarded_messages": [], "online_users": []}

def save_statistics(statistics):
    with open(STATISTICS_FILE, 'w') as f:
        json.dump(statistics, f, indent=4)

# Khởi tạo dữ liệu
whitelist = load_whitelist()
forward_rules = load_forward_rules()
allowed_users = load_users()
settings = load_settings()
statistics = load_statistics()

# Khởi tạo bot Telegram
application = Application.builder().token(BOT_TOKEN).build()

# Khởi tạo scheduler để lên lịch
scheduler = AsyncIOScheduler()
scheduler.start()

# Hàm kiểm tra quyền admin
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# Hàm kiểm tra người dùng được phép
def is_allowed_user(user_id: int) -> bool:
    return user_id in allowed_users or user_id in ADMIN_IDS

# Menu chính với emoji
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🔐 Đăng nhập tài khoản", callback_data="login"),
         InlineKeyboardButton("📥 Thêm nguồn", callback_data="add_source")],
        [InlineKeyboardButton("📤 Thêm đích", callback_data="add_target"),
         InlineKeyboardButton("▶️ Bắt đầu chuyển tiếp", callback_data="start_forward")],
        [InlineKeyboardButton("🚫 Blacklist", callback_data="blacklist"),
         InlineKeyboardButton("✅ Whitelist", callback_data="whitelist")],
        [InlineKeyboardButton("🔄 Thay thế nội dung", callback_data="replace"),
         InlineKeyboardButton("📅 Lên lịch tin nhắn", callback_data="schedule")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"),
         InlineKeyboardButton("📊 Thống kê", callback_data="stats")],
        [InlineKeyboardButton("📜 Danh sách nhóm/kênh", callback_data="list_chats"),
         InlineKeyboardButton("🧹 Cleaners Menu", callback_data="cleaners_menu")],  # Thay thế nút "Tham gia kênh tin tức"
        [InlineKeyboardButton("📋 Forwarding Menu", callback_data="forward_menu"),
         InlineKeyboardButton("👥 User Management", callback_data="user_menu")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu"),
         InlineKeyboardButton("📂 Filter Groups/Channels", callback_data="filter_menu")],
        [InlineKeyboardButton("📱 Recent Online Contacts", callback_data="recent_online"),
         InlineKeyboardButton("📈 Statistics", callback_data="statistics")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Menu Cleaners
def cleaners_menu(chat_id):
    cleaners = user_data.get(chat_id, {}).get("cleaners", {
        "text": False, "audio": False, "url": False, "url_preview": False,
        "video": False, "sticker": False, "hashtag": False, "mention": False,
        "photo": False, "document": False, "video_note": False, "voice": False,
        "emoji": False, "dice": False, "photo_with_text": False, "animation": False
    })
    keyboard = [
        [InlineKeyboardButton(f"{'✅' if cleaners['text'] else '🚫'} Text", callback_data="toggle_cleaner_text"),
         InlineKeyboardButton(f"{'✅' if cleaners['audio'] else '🚫'} Audio", callback_data="toggle_cleaner_audio")],
        [InlineKeyboardButton(f"{'✅' if cleaners['url'] else '🚫'} URL", callback_data="toggle_cleaner_url"),
         InlineKeyboardButton(f"{'✅' if cleaners['url_preview'] else '🚫'} URL Preview", callback_data="toggle_cleaner_url_preview")],
        [InlineKeyboardButton(f"{'✅' if cleaners['video'] else '🚫'} Video", callback_data="toggle_cleaner_video"),
         InlineKeyboardButton(f"{'✅' if cleaners['sticker'] else '🚫'} Sticker", callback_data="toggle_cleaner_sticker")],
        [InlineKeyboardButton(f"{'✅' if cleaners['hashtag'] else '🚫'} Hashtag", callback_data="toggle_cleaner_hashtag"),
         InlineKeyboardButton(f"{'✅' if cleaners['mention'] else '🚫'} Mention", callback_data="toggle_cleaner_mention")],
        [InlineKeyboardButton(f"{'✅' if cleaners['photo'] else '🚫'} Photo", callback_data="toggle_cleaner_photo"),
         InlineKeyboardButton(f"{'✅' if cleaners['document'] else '🚫'} Document", callback_data="toggle_cleaner_document")],
        [InlineKeyboardButton(f"{'✅' if cleaners['video_note'] else '🚫'} Video Note", callback_data="toggle_cleaner_video_note"),
         InlineKeyboardButton(f"{'✅' if cleaners['voice'] else '🚫'} Voice", callback_data="toggle_cleaner_voice")],
        [InlineKeyboardButton(f"{'✅' if cleaners['emoji'] else '🚫'} Emoji", callback_data="toggle_cleaner_emoji"),
         InlineKeyboardButton(f"{'✅' if cleaners['dice'] else '🚫'} Dice", callback_data="toggle_cleaner_dice")],
        [InlineKeyboardButton(f"{'✅' if cleaners['photo_with_text'] else '🚫'} Photo with Text", callback_data="toggle_cleaner_photo_with_text"),
         InlineKeyboardButton(f"{'✅' if cleaners['animation'] else '🚫'} Animation", callback_data="toggle_cleaner_animation")],
        [InlineKeyboardButton("❓ How do I use this?", callback_data="cleaners_help")],
        [InlineKeyboardButton("⬅️ Return to Main Menu", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Nút quay lại
def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="back")]])

# Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    await update.message.reply_text("Chào mừng bạn! Chọn hành động:", reply_markup=main_menu())

# Hàm bất đồng bộ để liệt kê nhóm/kênh
async def list_chats_async(chat_id, query):
    if chat_id not in clients:
        await query.edit_message_text(text="Vui lòng đăng nhập trước!", reply_markup=main_menu())
        return
    chats = []
    async for dialog in clients[chat_id].iter_dialogs():
        username = dialog.entity.username if hasattr(dialog.entity, "username") and dialog.entity.username else "Không có"
        chats.append(f"{dialog.name} (@{username}) - ID: {dialog.entity.id}")
    text = "📜 Danh sách nhóm/kênh:\n" + "\n".join(chats) if chats else "Không tìm thấy nhóm/kênh nào!“
    await query.edit_message_text(text=text, reply_markup=back_button())

# Xử lý nút
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if not is_allowed_user(user_id):
        await query.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    # Khởi tạo cleaners nếu chưa có
    if chat_id not in user_data:
        user_data[chat_id] = {}
    if "cleaners" not in user_data[chat_id]:
        user_data[chat_id]["cleaners"] = {
            "text": False, "audio": False, "url": False, "url_preview": False,
            "video": False, "sticker": False, "hashtag": False, "mention": False,
            "photo": False, "document": False, "video_note": False, "voice": False,
            "emoji": False, "dice": False, "photo_with_text": False, "animation": False
        }

    if query.data == "login":
        await query.edit_message_text(text="Gửi số điện thoại của bạn (ví dụ: +84123456789):", reply_markup=back_button())
        context.user_data["state"] = "waiting_phone"

    elif query.data == "add_source":
        await query.edit_message_text(text="Gửi user_id của kênh/nhóm nguồn (ví dụ: -100123456789):", reply_markup=back_button())
        context.user_data["state"] = "waiting_source"

    elif query.data == "add_target":
        await query.edit_message_text(text="Gửi user_id của kênh/nhóm đích (ví dụ: -100987654321):", reply_markup=back_button())
        context.user_data["state"] = "waiting_target"

    elif query.data == "start_forward":
        if chat_id not in clients:
            await query.edit_message_text(text="Vui lòng đăng nhập tài khoản trước!", reply_markup=main_menu())
        elif "source" not in user_data.get(chat_id, {}) or "target" not in user_data.get(chat_id, {}):
            await query.edit_message_text(text="Vui lòng thêm nguồn và đích trước!", reply_markup=main_menu())
        else:
            await query.edit_message_text(text="▶️ Đã bắt đầu chuyển tiếp!", reply_markup=main_menu())
            start_forwarding(chat_id, context)

    elif query.data == "blacklist":
        keyboard = [
            [InlineKeyboardButton("Thêm từ khóa", callback_data="add_blacklist_word"),
             InlineKeyboardButton("Thêm user_id", callback_data="add_blacklist_id")],
            [InlineKeyboardButton("Xem danh sách", callback_data="view_blacklist"),
             InlineKeyboardButton("Quay lại", callback_data="back")]
        ]
        await query.edit_message_text(text="🚫 Quản lý Blacklist:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "whitelist":
        keyboard = [
            [InlineKeyboardButton("Thêm từ khóa", callback_data="add_whitelist_word"),
             InlineKeyboardButton("Thêm user_id", callback_data="add_whitelist_id")],
            [InlineKeyboardButton("Xem danh sách", callback_data="view_whitelist"),
             InlineKeyboardButton("Quay lại", callback_data="back")]
        ]
        await query.edit_message_text(text="✅ Quản lý Whitelist:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("add_blacklist"):
        target = "word" if query.data == "add_blacklist_word" else "id"
        await query.edit_message_text(text=f"Gửi {'từ khóa' if target == 'word' else 'user_id'} để thêm vào blacklist:", reply_markup=back_button())
        context.user_data["state"] = f"waiting_blacklist_{target}"

    elif query.data.startswith("add_whitelist"):
        target = "word" if query.data == "add_whitelist_word" else "id"
        await query.edit_message_text(text=f"Gửi {'từ khóa' if target == 'word' else 'user_id'} để thêm vào whitelist:", reply_markup=back_button())
        context.user_data["state"] = f"waiting_whitelist_{target}"

    elif query.data == "view_blacklist":
        blacklist = user_data.get(chat_id, {}).get("blacklist", {"words": [], "ids": []})
        text = f"Blacklist:\nTừ khóa: {', '.join(blacklist['words']) or 'Trống'}\nUser_ID: {', '.join(map(str, blacklist['ids'])) or 'Trống'}"
        await query.edit_message_text(text=text, reply_markup=back_button())

    elif query.data == "view_whitelist":
        whitelist_data = user_data.get(chat_id, {}).get("whitelist", {"words": [], "ids": []})
        text = f"Whitelist:\nTừ khóa: {', '.join(whitelist_data['words']) or 'Trống'}\nUser_ID: {', '.join(map(str, whitelist_data['ids'])) or 'Trống'}"
        await query.edit_message_text(text=text, reply_markup=back_button())

    elif query.data == "replace":
        keyboard = [
            [InlineKeyboardButton("📝 Thay thế văn bản", callback_data="replace_text"),
             InlineKeyboardButton("😊 Thay thế emoji", callback_data="replace_emoji")],
            [InlineKeyboardButton("🖼️ Thay thế media", callback_data="replace_media"),
             InlineKeyboardButton("🔙 Quay lại", callback_data="back")]
        ]
        await query.edit_message_text(text="🔄 Chọn loại thay thế:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "replace_text":
        await query.edit_message_text(text="📝 Nhập cặp từ thay thế (ví dụ: hello=>hi):", reply_markup=back_button())
        context.user_data["state"] = "waiting_replace_text"

    elif query.data == "replace_emoji":
        await query.edit_message_text(text="😊 Nhập cặp emoji thay thế (ví dụ: 😊=>😄):", reply_markup=back_button())
        context.user_data["state"] = "waiting_replace_emoji"

    elif query.data == "replace_media":
        await query.edit_message_text(text="🖼️ Tính năng thay thế media đang phát triển!", reply_markup=main_menu())

    elif query.data == "schedule":
        await query.edit_message_text(text="⏰ Nhập thời gian và nội dung (ví dụ: 1m Tin nhắn tự động):", reply_markup=back_button())
        context.user_data["state"] = "waiting_schedule"

    elif query.data == "broadcast_menu":
        broadcast_enabled = user_data.get(chat_id, {}).get("broadcast_enabled", False)
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast đến nhóm", callback_data="broadcast_groups"),
             InlineKeyboardButton("📢 Broadcast đến danh bạ", callback_data="broadcast_contacts")],
            [InlineKeyboardButton("📢 Broadcast đến tất cả", callback_data="broadcast_all"),
             InlineKeyboardButton("🔙 Quay lại", callback_data="back")],
            [InlineKeyboardButton("▶️ Bắt đầu Broadcast" if not broadcast_enabled else "⏹ Kết thúc Broadcast",
                                  callback_data="start_broadcast" if not broadcast_enabled else "stop_broadcast")]
        ]
        status = "đang chạy" if broadcast_enabled else "đã dừng"
        await query.edit_message_text(text=f"📢 Chọn loại broadcast (Trạng thái: {status}):", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "broadcast_groups":
        user_data[chat_id]["broadcast_target"] = "groups"
        await query.edit_message_text(text="📢 Nhập nội dung broadcast đến các nhóm (hoặc gửi media để chuyển tiếp):", reply_markup=back_button())
        context.user_data["state"] = "waiting_broadcast_groups"

    elif query.data == "broadcast_contacts":
        user_data[chat_id]["broadcast_target"] = "contacts"
        await query.edit_message_text(text="📢 Nhập nội dung broadcast đến danh bạ (hoặc gửi media để chuyển tiếp):", reply_markup=back_button())
        context.user_data["state"] = "waiting_broadcast_contacts"

    elif query.data == "broadcast_all":
        user_data[chat_id]["broadcast_target"] = "all"
        await query.edit_message_text(text="📢 Nhập nội dung broadcast đến tất cả (hoặc gửi media để chuyển tiếp):", reply_markup=back_button())
        context.user_data["state"] = "waiting_broadcast_all"

    elif query.data == "start_broadcast":
        if chat_id not in clients:
            await query.edit_message_text(text="Vui lòng đăng nhập tài khoản trước!", reply_markup=main_menu())
        elif "source" not in user_data.get(chat_id, {}):
            await query.edit_message_text(text="Vui lòng thêm nguồn trước!", reply_markup=main_menu())
        elif "broadcast_target" not in user_data.get(chat_id, {}):
            await query.edit_message_text(text="Vui lòng chọn loại broadcast trước (nhóm, danh bạ, hoặc tất cả)!", reply_markup=main_menu())
        else:
            user_data[chat_id]["broadcast_enabled"] = True
            setup_broadcast(chat_id)
            await query.edit_message_text(text="▶️ Đã bắt đầu broadcast!", reply_markup=main_menu())

    elif query.data == "stop_broadcast":
        user_data[chat_id]["broadcast_enabled"] = False
        await query.edit_message_text(text="⏹ Đã kết thúc broadcast!", reply_markup=main_menu())

    elif query.data == "cleaners_menu":
        await query.edit_message_text(
            text="🧹 Cleaners Menu 🧹\n\n"
                 "Use this menu to remove specific content from messages when forwarding or broadcasting.\n"
                 "Toggle the cleaners to activate/deactivate them.",
            reply_markup=cleaners_menu(chat_id)
        )

    elif query.data.startswith("toggle_cleaner_"):
        cleaner_type = query.data.replace("toggle_cleaner_", "")
        user_data[chat_id]["cleaners"][cleaner_type] = not user_data[chat_id]["cleaners"][cleaner_type]
        await query.edit_message_text(
            text="🧹 Cleaners Menu 🧹\n\n"
                 "Use this menu to remove specific content from messages when forwarding or broadcasting.\n"
                 "Toggle the cleaners to activate/deactivate them.",
            reply_markup=cleaners_menu(chat_id)
        )

    elif query.data == "cleaners_help":
        await query.edit_message_text(
            text="❓ How do I use Cleaners? ❓\n\n"
                 "Cleaners allow you to filter out specific content from messages when forwarding or broadcasting.\n\n"
                 "🔹 Toggle a cleaner to ✅ to remove that content type (e.g., Text, Photo, URL).\n"
                 "🔹 Toggle it to 🚫 to allow that content type.\n\n"
                 "Examples:\n"
                 "- If 'Text' is ✅, all text will be removed from messages.\n"
                 "- If 'Photo' is ✅, photos will be skipped during forwarding.\n\n"
                 "Use this to customize the content you want to forward or broadcast!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Return", callback_data="cleaners_menu")]])
        )

    elif query.data == "stats":
        await statistics_command(query.message, context)

    elif query.data == "list_chats":
        await list_chats_async(chat_id, query)

    elif query.data == "forward_menu":
        keyboard = [
            [InlineKeyboardButton("Clear All", callback_data="forward_clear"),
             InlineKeyboardButton("Show All", callback_data="forward_show")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📢 Forwarding Assistance Menu 📢\n\n"
                                      "Use this menu to configure auto message forwarding.\n\n"
                                      "📖 Before using this command, retrieve chat IDs using /getchatid, /getgroup, or /getuser.\n\n"
                                      "Follow the format below when adding channels, users, or bots:\n"
                                      "/forward ACTION LABEL SOURCE_CHAT_ID -> TARGET_CHAT_ID\n\n"
                                      "❗ Note: The LABEL should not contain spaces or special characters. Keep it simple.\n\n"
                                      "========== Examples ==========\n\n"
                                      "🔹 One-to-One Chat\n"
                                      "/forward add work1 2222 -> 66666\n\n"
                                      "🔹 Many-to-One Chat\n"
                                      "/forward add work2 2222,33333 -> 66666\n\n"
                                      "🔹 One-to-Many Chat\n"
                                      "/forward add work3 2222 -> 66666,77777\n\n"
                                      "🔹 Many-to-Many Chat\n"
                                      "/forward add work4 2222,33333 -> 66666,77777\n\n"
                                      "🔹 Remove Rule\n"
                                      "/forward remove work1", reply_markup=reply_markup)

    elif query.data == "user_menu":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể quản lý người dùng!", reply_markup=main_menu())
            return
        await query.edit_message_text("📋 User Management Menu 📋\n\n"
                                      "Use these commands to manage users:\n"
                                      "/user add USER_ID - Thêm người dùng\n"
                                      "/user remove USER_ID - Xóa người dùng\n"
                                      "/user list - Hiển thị danh sách người dùng", reply_markup=back_button())

    elif query.data == "settings_menu":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        keyboard = [
            [InlineKeyboardButton("Toggle Forward: " + ("ON" if settings["forward_enabled"] else "OFF"),
                                  callback_data="toggle_forward")],
            [InlineKeyboardButton("Toggle Whitelist: " + ("ON" if settings["whitelist_enabled"] else "OFF"),
                                  callback_data="toggle_whitelist")],
            [InlineKeyboardButton("Forward Mode: " + ("Forward" if settings["forward_mode"] == "forward" else "Copy"),
                                  callback_data="toggle_forward_mode")],
            [InlineKeyboardButton("Quay lại", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚙️ Settings Menu ⚙️\n\n"
                                      "Current Settings:\n"
                                      f"Forwarding: {'Enabled' if settings['forward_enabled'] else 'Disabled'}\n"
                                      f"Whitelist: {'Enabled' if settings['whitelist_enabled'] else 'Disabled'}\n"
                                      f"Forward Mode: {settings['forward_mode'].capitalize()}\n",
                                      reply_markup=reply_markup)

    elif query.data == "toggle_forward":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings["forward_enabled"] = not settings["forward_enabled"]
        save_settings(settings)
        await query.edit_message_text(f"Forwarding đã được {'bật' if settings['forward_enabled'] else 'tắt'}.", reply_markup=main_menu())

    elif query.data == "toggle_whitelist":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings["whitelist_enabled"] = not settings["whitelist_enabled"]
        save_settings(settings)
        await query.edit_message_text(f"Whitelist đã được {'bật' if settings['whitelist_enabled'] else 'tắt'}.", reply_markup=main_menu())

    elif query.data == "toggle_forward_mode":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings["forward_mode"] = "copy" if settings["forward_mode"] == "forward" else "forward"
        save_settings(settings)
        await query.edit_message_text(f"Forward Mode đã được chuyển thành {'Copy' if settings['forward_mode'] == 'copy' else 'Forward'}.", reply_markup=main_menu())

    elif query.data == "forward_clear":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể xóa quy tắc forward!", reply_markup=main_menu())
            return
        forward_rules[chat_id] = {}
        save_forward_rules(forward_rules)
        await query.edit_message_text("Đã xóa tất cả quy tắc forward.", reply_markup=main_menu())

    elif query.data == "forward_show":
        if chat_id not in forward_rules or not forward_rules[chat_id]:
            await query.edit_message_text("Hiện tại không có quy tắc forward nào.", reply_markup=main_menu())
            return
        response = "📋 Danh sách quy tắc forward:\n\n"
        for label, rule in forward_rules[chat_id].items():
            response += f"🔹 {label}: {rule['source_chat_ids']} -> {rule['target_chat_ids']}\n"
        await query.edit_message_text(response, reply_markup=back_button())

    elif query.data == "filter_menu":
        await query.edit_message_text("📂 Filter Menu 📂\n\n"
                                      "Use these commands to filter groups, channels, or usernames:\n"
                                      "/filtergroups - Lọc danh sách nhóm\n"
                                      "/filterchannels - Lọc danh sách kênh\n"
                                      "/filterusername USERNAME - Tìm kiếm theo username", reply_markup=back_button())

    elif query.data == "recent_online":
        await recent_online(query.message, context)

    elif query.data == "statistics":
        await statistics_command(query.message, context)

    elif query.data == "back":
        await query.edit_message_text(text="Chào mừng! Chọn hành động:", reply_markup=main_menu())

# Xử lý tin nhắn từ người dùng
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    text = update.message.text
    message = update.message

    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    user_data[chat_id] = user_data.get(chat_id, {})
    if "state" not in context.user_data:
        return

    state = context.user_data["state"]

    if state == "waiting_phone":
        user_data[chat_id]["phone"] = text
        client = TelegramClient(f"sessions/{chat_id}_{text}", API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(text)
            await update.message.reply_text("Gửi mã OTP bạn nhận được:", reply_markup=back_button())
            context.user_data["state"] = "waiting_code"
            context.user_data["client"] = client
        else:
            clients[chat_id] = client
            setup_forwarding(chat_id)
            setup_broadcast(chat_id)  # Thiết lập broadcast sau khi đăng nhập
            await update.message.reply_text("Đã đăng nhập thành công từ phiên trước!", reply_markup=main_menu())
            context.user_data["state"] = None

    elif state == "waiting_code":
        client = context.user_data["client"]
        try:
            await client.sign_in(code=text)
            clients[chat_id] = client
            setup_forwarding(chat_id)
            setup_broadcast(chat_id)  # Thiết lập broadcast sau khi đăng nhập
            await update.message.reply_text("Đăng nhập thành công!", reply_markup=main_menu())
        except SessionPasswordNeededError:
            await update.message.reply_text("Tài khoản yêu cầu mật khẩu xác minh hai bước. Nhập mật khẩu:", reply_markup=back_button())
            context.user_data["state"] = "waiting_password"
        except Exception as e:
            await update.message.reply_text(f"Lỗi: {str(e)}. Vui lòng thử lại.", reply_markup=main_menu())
            context.user_data["state"] = None

    elif state == "waiting_password":
        client = context.user_data["client"]
        try:
            await client.sign_in(password=text)
            clients[chat_id] = client
            setup_forwarding(chat_id)
            setup_broadcast(chat_id)  # Thiết lập broadcast sau khi đăng nhập
            await update.message.reply_text("Đăng nhập thành công!", reply_markup=main_menu())
        except Exception as e:
            await update.message.reply_text(f"Lỗi: {str(e)}. Vui lòng thử lại.", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_source":
        user_data[chat_id]["source"] = int(text)
        await update.message.reply_text(f"Nguồn đã đặt: {text}", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_target":
        user_data[chat_id]["target"] = int(text)
        await update.message.reply_text(f"Đích đã đặt: {text}", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state.startswith("waiting_blacklist"):
        target = "words" if state == "waiting_blacklist_word" else "ids"
        user_data[chat_id]["blacklist"] = user_data[chat_id].get("blacklist", {"words": [], "ids": []})
        value = text if target == "words" else int(text)
        user_data[chat_id]["blacklist"][target].append(value)
        await update.message.reply_text(f"Đã thêm {value} vào blacklist!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state.startswith("waiting_whitelist"):
        target = "words" if state == "waiting_whitelist_word" else "ids"
        user_data[chat_id]["whitelist"] = user_data[chat_id].get("whitelist", {"words": [], "ids": []})
        value = text if target == "words" else int(text)
        user_data[chat_id]["whitelist"][target].append(value)
        await update.message.reply_text(f"Đã thêm {value} vào whitelist!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_replace_text":
        try:
            key, value = text.split("=>")
            user_data[chat_id]["replace_dict"] = user_data[chat_id].get("replace_dict", {})
            user_data[chat_id]["replace_dict"][key.strip()] = value.strip()
            await update.message.reply_text(f"Đã thêm thay thế: {key} => {value}", reply_markup=main_menu())
        except:
            await update.message.reply_text("Định dạng không đúng! Vui lòng nhập lại (ví dụ: hello=>hi).", reply_markup=back_button())
        context.user_data["state"] = None

    elif state == "waiting_replace_emoji":
        try:
            key, value = text.split("=>")
            user_data[chat_id]["emoji_replace"] = user_data[chat_id].get("emoji_replace", {})
            user_data[chat_id]["emoji_replace"][key.strip()] = value.strip()
            await update.message.reply_text(f"Đã thêm thay thế emoji: {key} => {value}", reply_markup=main_menu())
        except:
            await update.message.reply_text("Định dạng không đúng! Vui lòng nhập lại (ví dụ: 😊=>😄).", reply_markup=back_button())
        context.user_data["state"] = None

    elif state == "waiting_schedule":
        try:
            parts = text.split(" ", 1)
            interval, message = parts[0], parts[1]
            interval_minutes = int(interval.replace("m", ""))
            target = user_data[chat_id]["target"]
            scheduler.add_job(scheduled_message, 'interval', minutes=interval_minutes, args=[clients[chat_id], target, message])
            await update.message.reply_text(f"⏰ Đã lên lịch gửi tin nhắn mỗi {interval_minutes} phút: {message}", reply_markup=main_menu())
        except:
            await update.message.reply_text("Định dạng không đúng! Vui lòng nhập lại (ví dụ: 1m Tin nhắn tự động).", reply_markup=back_button())
        context.user_data["state"] = None

    elif state == "waiting_broadcast_groups":
        if chat_id in clients:
            await broadcast_message(clients[chat_id], message, target="groups")
            await update.message.reply_text("📢 Đã gửi tin nhắn hàng loạt đến các nhóm!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_broadcast_contacts":
        if chat_id in clients:
            await broadcast_message(clients[chat_id], message, target="contacts")
            await update.message.reply_text("📢 Đã gửi tin nhắn hàng loạt đến danh bạ!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_broadcast_all":
        if chat_id in clients:
            await broadcast_message(clients[chat_id], message, target="all")
            await update.message.reply_text("📢 Đã gửi tin nhắn hàng loạt đến tất cả!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

# Hàm xử lý lệnh /start_broadcast
async def start_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.effective_user.id

    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập tài khoản trước!")
        return

    if "source" not in user_data.get(chat_id, {}):
        await update.message.reply_text("Vui lòng thêm nguồn trước!")
        return

    if "broadcast_target" not in user_data.get(chat_id, {}):
        await update.message.reply_text("Vui lòng chọn loại broadcast trước (nhóm, danh bạ, hoặc tất cả)!")
        return

    user_data[chat_id]["broadcast_enabled"] = True
    setup_broadcast(chat_id)
    await update.message.reply_text("▶️ Đã bắt đầu broadcast!")

# Hàm xử lý lệnh /stop_broadcast
async def stop_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.effective_user.id

    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    user_data[chat_id]["broadcast_enabled"] = False
    await update.message.reply_text("⏹ Đã kết thúc broadcast!")

# Hàm xử lý lệnh /forward
async def forward_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_admin(user_id):
        await update.message.reply_text("Chỉ admin mới có thể cấu hình forward!")
        return

    if not context.args or len(context.args) < 3:
        keyboard = [
            [InlineKeyboardButton("Clear All", callback_data="forward_clear"),
             InlineKeyboardButton("Show All", callback_data="forward_show")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📢 Forwarding Assistance Menu 📢\n\n"
                                        "Use this menu to configure auto message forwarding.\n\n"
                                        "📖 Before using this command, retrieve chat IDs using /getchatid, /getgroup, or /getuser.\n\n"
                                        "Follow the format below when adding channels, users, or bots:\n"
                                        "/forward ACTION LABEL SOURCE_CHAT_ID -> TARGET_CHAT_ID\n\n"
                                        "❗ Note: The LABEL should not contain spaces or special characters. Keep it simple.\n\n"
                                        "========== Examples ==========\n\n"
                                        "🔹 One-to-One Chat\n"
                                        "/forward add work1 2222 -> 66666\n\n"
                                        "🔹 Many-to-One Chat\n"
                                        "/forward add work2 2222,33333 -> 66666\n\n"
                                        "🔹 One-to-Many Chat\n"
                                        "/forward add work3 2222 -> 66666,77777\n\n"
                                        "🔹 Many-to-Many Chat\n"
                                        "/forward add work4 2222,33333 -> 66666,77777\n\n"
                                        "🔹 Remove Rule\n"
                                        "/forward remove work1", reply_markup=reply_markup)
        return

    try:
        action = context.args[0].lower()
        label = context.args[1]

        if action not in ["add", "remove"]:
            await update.message.reply_text("Hành động không hợp lệ! Sử dụng 'add' hoặc 'remove'.")
            return

        if action == "add":
            command_text = " ".join(context.args[2:])
            if "->" not in command_text:
                await update.message.reply_text("Cú pháp không hợp lệ! Sử dụng: /forward add LABEL SOURCE_CHAT_ID -> TARGET_CHAT_ID")
                return

            source_part, target_part = command_text.split("->")
            source_chat_ids = [int(chat_id.strip()) for chat_id in source_part.split(",") if chat_id.strip()]
            target_chat_ids = [int(chat_id.strip()) for chat_id in target_part.split(",") if chat_id.strip()]

            if not source_chat_ids or not target_chat_ids:
                await update.message.reply_text("Vui lòng cung cấp SOURCE_CHAT_ID và TARGET_CHAT_ID hợp lệ!")
                return

            if not re.match(r'^[a-zA-Z0-9_]+$', label):
                await update.message.reply_text("LABEL không được chứa khoảng trắng hoặc ký tự đặc biệt!")
                return

            if chat_id not in forward_rules:
                forward_rules[chat_id] = {}
            forward_rules[chat_id][label] = {
                "source_chat_ids": source_chat_ids,
                "target_chat_ids": target_chat_ids
            }
            save_forward_rules(forward_rules)
            await update.message.reply_text(f"Đã thêm quy tắc forward với label '{label}'.")

        elif action == "remove":
            if chat_id in forward_rules and label in forward_rules[chat_id]:
                del forward_rules[chat_id][label]
                if not forward_rules[chat_id]:
                    del forward_rules[chat_id]
                save_forward_rules(forward_rules)
                await update.message.reply_text(f"Đã xóa quy tắc forward với label '{label}'.")
            else:
                await update.message.reply_text(f"Không tìm thấy quy tắc forward với label '{label}'.")

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /whitelist
async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_admin(user_id):
        await update.message.reply_text("Chỉ admin mới có thể cấu hình whitelist!")
        return

    if not context.args:
        await update.message.reply_text("❇️ Whitelist Help Menu ❇️\n\n"
                                        "Basic Command:\n/whitelist ACTION LABEL WORD_LIST\n\n"
                                        "Advanced Command (Regex):\n/whitelist ACTION LABEL_regex WORD_LIST\n"
                                        "/whitelist ACTION LABEL_user LIST_USER\n\n"
                                        "📖 WORD_LIST: Distinguish between uppercase and lowercase letters\n"
                                        "📖 LIST_USER: It could be User ID or username\n\n"
                                        "✅ Basic Examples:\n"
                                        "➡️ /whitelist add label1 copyright\n"
                                        "➡️ /whitelist add label1 copyright,DMCA\n\n"
                                        "✅ Advanced Examples:\n"
                                        "➡️ /whitelist add label1_regex (black|white)\n"
                                        "➡️ /whitelist add group1_user zinREAL,410995490\n"
                                        "➡️ /whitelist add label1_regex hello==AND==bye\n"
                                        "➡️ /whitelist remove label1")
        return

    try:
        action = context.args[0].lower()
        label = context.args[1]
        items = context.args[2] if len(context.args) > 2 else ""

        if action not in ["add", "remove"]:
            await update.message.reply_text("Hành động không hợp lệ! Sử dụng 'add' hoặc 'remove'.")
            return

        if action == "add":
            if not items:
                await update.message.reply_text("Vui lòng cung cấp WORD_LIST hoặc LIST_USER!")
                return

            if chat_id not in whitelist:
                whitelist[chat_id] = {}
            if label.endswith("_regex"):
                whitelist[chat_id][label] = {"type": "regex", "pattern": items}
            elif label.endswith("_user"):
                user_list = [item.strip() for item in items.split(",")]
                whitelist[chat_id][label] = {"type": "user", "users": user_list}
            else:
                word_list = [word.strip() for word in items.split(",")]
                whitelist[chat_id][label] = {"type": "word", "words": word_list}

            save_whitelist(whitelist)
            await update.message.reply_text(f"Đã thêm whitelist với label '{label}'.")

        elif action == "remove":
            if chat_id in whitelist and label in whitelist[chat_id]:
                del whitelist[chat_id][label]
                if not whitelist[chat_id]:
                    del whitelist[chat_id]
                save_whitelist(whitelist)
                await update.message.reply_text(f"Đã xóa whitelist với label '{label}'.")
            else:
                await update.message.reply_text(f"Không tìm thấy whitelist với label '{label}'.")

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /user
async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Chỉ admin mới có thể quản lý người dùng!")
        return

    if not context.args:
        await update.message.reply_text("📋 User Management Menu 📋\n\n"
                                        "Use these commands to manage users:\n"
                                        "/user add USER_ID - Thêm người dùng\n"
                                        "/user remove USER_ID - Xóa người dùng\n"
                                        "/user list - Hiển thị danh sách người dùng")
        return

    try:
        action = context.args[0].lower()
        if action == "add":
            new_user_id = int(context.args[1])
            if new_user_id not in allowed_users:
                allowed_users.append(new_user_id)
                save_users(allowed_users)
                await update.message.reply_text(f"Đã thêm người dùng {new_user_id}.")
            else:
                await update.message.reply_text(f"Người dùng {new_user_id} đã có trong danh sách.")

        elif action == "remove":
            user_id_to_remove = int(context.args[1])
            if user_id_to_remove in allowed_users:
                allowed_users.remove(user_id_to_remove)
                save_users(allowed_users)
                await update.message.reply_text(f"Đã xóa người dùng {user_id_to_remove}.")
            else:
                await update.message.reply_text(f"Không tìm thấy người dùng {user_id_to_remove}.")

        elif action == "list":
            if not allowed_users:
                await update.message.reply_text("Hiện tại không có người dùng nào được phép.")
                return
            response = "📋 Danh sách người dùng được phép:\n\n"
            for user_id in allowed_users:
                response += f"🔹 {user_id}\n"
            await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /getchatid, /getgroup, /getuser
async def getchatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Chat ID: {chat_id}")

async def getgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Lệnh này chỉ hoạt động trong group!")
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Group ID: {chat_id}")

async def getuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    user_id = update.effective_user.id
    await update.message.reply_text(f"User ID: {user_id}")

# Hàm xử lý lệnh /filtergroups
async def filter_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return

    try:
        dialogs = await clients[chat_id].get_dialogs()
        groups = [d for d in dialogs if d.is_group]
        if not groups:
            await update.message.reply_text("Không tìm thấy nhóm nào!")
            return

        response = "📋 Danh sách nhóm:\n\n"
        for group in groups:
            response += f"🔹 {group.title} (ID: {group.id})\n"
        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /filterchannels
async def filter_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return

    try:
        dialogs = await clients[chat_id].get_dialogs()
        channels = [d for d in dialogs if d.is_channel]
        if not channels:
            await update.message.reply_text("Không tìm thấy kênh nào!")
            return

        response = "📋 Danh sách kênh:\n\n"
        for channel in channels:
            response += f"🔹 {channel.title} (ID: {channel.id})\n"
        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /filterusername
async def filter_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return

    if not context.args:
        await update.message.reply_text("Vui lòng cung cấp username! Ví dụ: /filterusername username")
        return

    username = context.args[0].strip()
    try:
        entity = await clients[chat_id].get_entity(username)
        response = "📋 Kết quả tìm kiếm:\n\n"
        if hasattr(entity, 'title'):
            response += f"🔹 {entity.title} (ID: {entity.id}, Type: {'Channel' if entity.broadcast else 'Group'})\n"
        else:
            response += f"🔹 {entity.first_name} {entity.last_name or ''} (ID: {entity.id}, Type: User, Username: @{entity.username})\n"
        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /recentonline
async def recent_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return

    try:
        contacts = await clients[chat_id].get_contacts()
        if not contacts:
            await update.message.reply_text("Danh bạ của bạn trống!")
            return

        online_users = []
        for user in contacts:
            status = user.status
            if isinstance(status, UserStatusOnline):
                online_users.append((user, "Online"))
            elif isinstance(status, UserStatusRecently):
                online_users.append((user, "Recently Online"))
            elif isinstance(status, UserStatusLastWeek):
                online_users.append((user, "Last Week"))
            elif isinstance(status, UserStatusLastMonth):
                online_users.append((user, "Last Month"))

        if not online_users:
            await update.message.reply_text("Không có người dùng nào online gần đây trong danh bạ!")
            return

        online_users.sort(key=lambda x: ["Online", "Recently Online", "Last Week", "Last Month"].index(x[1]))

        response = "📋 Danh sách người dùng online gần nhất:\n\n"
        for user, status in online_users[:10]:
            response += f"🔹 {user.first_name} {user.last_name or ''} (@{user.username or 'N/A'}) - {status}\n"
            statistics["online_users"].append({
                "user_id": user.id,
                "username": user.username,
                "status": status,
                "timestamp": datetime.now().isoformat()
            })

        save_statistics(statistics)
        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Hàm xử lý lệnh /statistics
async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    try:
        start_time = datetime(2025, 3, 22, 0, 0, 0)
        end_time = datetime.now()

        forwarded_count = sum(1 for msg in statistics["forwarded_messages"]
                             if start_time <= datetime.fromisoformat(msg["timestamp"]) <= end_time)

        online_count = sum(1 for user in statistics["online_users"]
                           if start_time <= datetime.fromisoformat(user["timestamp"]) <= end_time)

        response = "📊 Thống kê từ 00:00 22/03/2025 đến 11:02 23/03/2025 📊\n\n"
        response += f"Số tin nhắn đã chuyển tiếp: {forwarded_count}\n"
        response += f"Số người dùng online (đã kiểm tra): {online_count}\n"

        await update.reply_text(response)

    except Exception as e:
        await update.reply_text(f"Lỗi: {str(e)}")

# Hàm thay thế nội dung
def replace_content(chat_id, text):
    replace_dict = user_data.get(chat_id, {}).get("replace_dict", {})
    emoji_replace = user_data.get(chat_id, {}).get("emoji_replace", {})
    
    for key, value in replace_dict.items():
        text = re.sub(r'\b' + key + r'\b', value, text, flags=re.IGNORECASE)
    
    for emoji, replacement in emoji_replace.items():
        text = text.replace(emoji, replacement)
    
    return text

# Hàm lọc nội dung dựa trên cleaners
def apply_cleaners(chat_id, message):
    cleaners = user_data.get(chat_id, {}).get("cleaners", {
        "text": False, "audio": False, "url": False, "url_preview": False,
        "video": False, "sticker": False, "hashtag": False, "mention": False,
        "photo": False, "document": False, "video_note": False, "voice": False,
        "emoji": False, "dice": False, "photo_with_text": False, "animation": False
    })
    msg_text = message.text or ""
    should_forward = True

    # Kiểm tra các bộ lọc
    if cleaners["text"] and msg_text:
        msg_text = ""
    if cleaners["url"] and msg_text:
        msg_text = re.sub(r'http[s]?://\S+|www\.\S+', '', msg_text)
    if cleaners["hashtag"] and msg_text:
        msg_text = re.sub(r'#\w+', '', msg_text)
    if cleaners["mention"] and msg_text:
        msg_text = re.sub(r'@\w+', '', msg_text)
    if cleaners["emoji"] and msg_text:
        msg_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', msg_text)
    if cleaners["photo"] and message.photo:
        should_forward = False
    if cleaners["photo_with_text"] and message.photo and msg_text:
        should_forward = False
    if cleaners["video"] and message.video:
        should_forward = False
    if cleaners["audio"] and message.audio:
        should_forward = False
    if cleaners["document"] and message.document:
        should_forward = False
    if cleaners["sticker"] and message.sticker:
        should_forward = False
    if cleaners["video_note"] and message.video_note:
        should_forward = False
    if cleaners["voice"] and message.voice:
        should_forward = False
    if cleaners["dice"] and message.dice:
        should_forward = False
    if cleaners["animation"] and message.animation:
        should_forward = False

    # Nếu không còn nội dung để gửi, bỏ qua tin nhắn
    if not should_forward and not msg_text:
        return None, None

    # Cập nhật nội dung tin nhắn
    message.text = msg_text
    return message, should_forward

# Hàm lên lịch gửi tin nhắn
async def scheduled_message(client, target, message):
    try:
        await client.send_message(target, message)
        logging.info(f"Đã gửi tin nhắn tự động đến {target}: {message}")
    except Exception as e:
        logging.error(f"Lỗi khi gửi tin nhắn tự động: {str(e)}")

# Hàm gửi tin nhắn hàng loạt
async def broadcast_message(client, message, target="all"):
    # Áp dụng cleaners trước khi broadcast
    chat_id = list(clients.keys())[list(clients.values()).index(client)]
    message, should_forward = apply_cleaners(chat_id, message)
    if not should_forward or message is None:
        return

    sent_to = set()
    async for dialog in client.iter_dialogs():
        should_send = False
        if target == "all":
            should_send = dialog.is_group or dialog.is_user
        elif target == "groups":
            should_send = dialog.is_group
        elif target == "contacts":
            should_send = dialog.is_user

        if should_send and dialog.entity.id not in sent_to:
            try:
                if settings["forward_mode"] == "forward":
                    await client.forward_messages(dialog.entity, message)
                else:  # copy mode
                    msg_text = message.text or ""
                    if message.media:
                        if message.photo:
                            await client.send_file(dialog.entity, message.photo, caption=msg_text)
                        elif message.video:
                            await client.send_file(dialog.entity, message.video, caption=msg_text)
                        elif message.document:
                            await client.send_file(dialog.entity, message.document, caption=msg_text)
                        else:
                            new_text = replace_content(chat_id, msg_text)
                            await client.send_message(dialog.entity, new_text)
                    else:
                        new_text = replace_content(chat_id, msg_text)
                        await client.send_message(dialog.entity, new_text)

                sent_to.add(dialog.entity.id)
                logging.info(f"Đã gửi broadcast đến {dialog.name}")
                await asyncio.sleep(1)  # Tránh giới hạn Telegram
            except Exception as e:
                logging.error(f"Lỗi khi gửi broadcast đến {dialog.name}: {str(e)}")

# Hàm kiểm tra tin nhắn có thỏa mãn whitelist không
def check_whitelist(chat_id, message_text: str, sender: dict) -> bool:
    if not settings["whitelist_enabled"] or chat_id not in whitelist or not whitelist[chat_id]:
        return True

    for label, config in whitelist[chat_id].items():
        if config["type"] == "word":
            for word in config["words"]:
                if word in message_text:
                    logger.info(f"Tin nhắn khớp với whitelist '{label}' (word: {word})")
                    return True

        elif config["type"] == "regex":
            pattern = config["pattern"]
            pattern = pattern.replace("==OR==", "|").replace("==AND==", ".*")
            try:
                if re.search(pattern, message_text):
                    logger.info(f"Tin nhắn khớp với whitelist '{label}' (regex: {pattern})")
                    return True
            except re.error as e:
                logger.error(f"Lỗi regex trong whitelist '{label}': {e}")
                continue

        elif config["type"] == "user":
            sender_id = str(sender.get("id", ""))
            sender_username = sender.get("username", "")
            for user in config["users"]:
                if user == sender_id or (sender_username and user.lower() == sender_username.lower()):
                    logger.info(f"Tin nhắn khớp với whitelist '{label}' (user: {user})")
                    return True

    logger.info("Tin nhắn không khớp với bất kỳ whitelist nào, bỏ qua.")
    return False

# Hàm bắt đầu chuyển tiếp với blacklist/whitelist
def start_forwarding(chat_id, context):
    client = clients[chat_id]
    source = user_data[chat_id]["source"]
    target = user_data[chat_id]["target"]
    blacklist = user_data[chat_id].get("blacklist", {"words": [], "ids": []})
    whitelist = user_data[chat_id].get("whitelist", {"words": [], "ids": []})

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        msg_text = event.message.text or ""
        sender_id = event.message.sender_id
        sender = await event.get_sender()
        sender_info = {
            "id": sender.id if sender else None,
            "username": sender.username if sender and hasattr(sender, "username") else None
        }

        # Kiểm tra blacklist
        if any(word.lower() in msg_text.lower() for word in blacklist["words"]) or sender_id in blacklist["ids"]:
            return

        # Kiểm tra whitelist
        if (whitelist["words"] or whitelist["ids"]) and not (any(word.lower() in msg_text.lower() for word in whitelist["words"]) or sender_id in whitelist["ids"]):
            return

        # Kiểm tra whitelist nâng cao
        if not check_whitelist(chat_id, msg_text, sender_info):
            return

        # Áp dụng cleaners
        message, should_forward = apply_cleaners(chat_id, event.message)
        if not should_forward or message is None:
            return

        # Xử lý tin nhắn theo forward_mode
        if settings["forward_mode"] == "forward":
            await client.forward_messages(target, message)
        else:  # copy mode
            if message.media:
                if message.photo:
                    await client.send_file(target, message.photo, caption=msg_text)
                elif message.video:
                    await client.send_file(target, message.video, caption=msg_text)
                elif message.document:
                    await client.send_file(target, message.document, caption=msg_text)
                else:
                    await client.send_message(target, msg_text)
            else:
                new_text = replace_content(chat_id, msg_text)
                await client.send_message(target, new_text)

        logging.info(f"Đã chuyển tiếp từ {source} đến {target}")

        # Ghi lại vào statistics
        statistics["forwarded_messages"].append({
            "from_chat_id": source,
            "to_chat_id": target,
            "message_id": event.message.id,
            "timestamp": datetime.now().isoformat()
        })
        save_statistics(statistics)

# Hàm thiết lập broadcast tự động
def setup_broadcast(chat_id):
    if chat_id not in clients:
        return

    client = clients[chat_id]
    source = user_data[chat_id]["source"]
    broadcast_target = user_data[chat_id].get("broadcast_target", "all")
    blacklist = user_data[chat_id].get("blacklist", {"words": [], "ids": []})
    whitelist = user_data[chat_id].get("whitelist", {"words": [], "ids": []})

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        if not user_data[chat_id].get("broadcast_enabled", False):
            return

        msg_text = event.message.text or ""
        sender_id = event.message.sender_id
        sender = await event.get_sender()
        sender_info = {
            "id": sender.id if sender else None,
            "username": sender.username if sender and hasattr(sender, "username") else None
        }

        # Kiểm tra blacklist
        if any(word.lower() in msg_text.lower() for word in blacklist["words"]) or sender_id in blacklist["ids"]:
            return

        # Kiểm tra whitelist
        if (whitelist["words"] or whitelist["ids"]) and not (any(word.lower() in msg_text.lower() for word in whitelist["words"]) or sender_id in whitelist["ids"]):
            return

        # Kiểm tra whitelist nâng cao
        if not check_whitelist(chat_id, msg_text, sender_info):
            return

        # Áp dụng cleaners
        message, should_forward = apply_cleaners(chat_id, event.message)
        if not should_forward or message is None:
            return

        # Broadcast tin nhắn
        await broadcast_message(client, message, target=broadcast_target)

        logging.info(f"Đã broadcast từ {source} đến {broadcast_target}")

        # Ghi lại vào statistics
        statistics["forwarded_messages"].append({
            "from_chat_id": source,
            "to_chat_id": broadcast_target,
            "message_id": event.message.id,
            "timestamp": datetime.now().isoformat()
        })
        save_statistics(statistics)

# Hàm forward tin nhắn theo quy tắc forward
async def forward_message(client, from_chat_id: int, message, target_chat_ids: list):
    chat_id = list(clients.keys())[list(clients.values()).index(client)]
    message, should_forward = apply_cleaners(chat_id, message)
    if not should_forward or message is None:
        return

    for target_chat_id in target_chat_ids:
        try:
            if settings["forward_mode"] == "forward":
                await client.forward_messages(target_chat_id, message)
            else:  # copy mode
                msg_text = message.text or ""
                if message.media:
                    if message.photo:
                        await client.send_file(target_chat_id, message.photo, caption=msg_text)
                    elif message.video:
                        await client.send_file(target_chat_id, message.video, caption=msg_text)
                    elif message.document:
                        await client.send_file(target_chat_id, message.document, caption=msg_text)
                    else:
                        await client.send_message(target_chat_id, msg_text)
                else:
                    new_text = replace_content(chat_id, msg_text)
                    await client.send_message(target_chat_id, new_text)

            logger.info(f"Đã chuyển tiếp tin nhắn từ {from_chat_id} đến {target_chat_id}")
            statistics["forwarded_messages"].append({
                "from_chat_id": from_chat_id,
                "to_chat_id": target_chat_id,
                "message_id": message.id,
                "timestamp": datetime.now().isoformat()
            })
            save_statistics(statistics)
        except Exception as e:
            logger.error(f"Lỗi khi chuyển tiếp tin nhắn đến {target_chat_id}: {e}")

# Xử lý chuyển tiếp theo quy tắc forward
def setup_forwarding(chat_id):
    if chat_id not in clients or not settings["forward_enabled"]:
        return

    client = clients[chat_id]
    if chat_id not in forward_rules or not forward_rules[chat_id]:
        return

    @client.on(events.NewMessage())
    async def handler(event):
        if not settings["forward_enabled"]:
            return

        message_text = event.message.text or ""
        sender = await event.get_sender()
        sender_info = {
            "id": sender.id if sender else None,
            "username": sender.username if sender and hasattr(sender, "username") else None
        }

        chat_id_event = event.chat_id
        target_chat_ids = []
        for label, rule in forward_rules[chat_id].items():
            if chat_id_event in rule["source_chat_ids"]:
                target_chat_ids.extend(rule["target_chat_ids"])

        if not target_chat_ids:
            return

        if check_whitelist(chat_id, message_text, sender_info):
            await forward_message(client, chat_id_event, event.message, target_chat_ids)

# Đăng ký lệnh và xử lý
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button))
application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
application.add_handler(CommandHandler("forward", forward_command))
application.add_handler(CommandHandler("whitelist", whitelist_command))
application.add_handler(CommandHandler("user", user_command))
application.add_handler(CommandHandler("getchatid", getchatid))
application.add_handler(CommandHandler("getgroup", getgroup))
application.add_handler(CommandHandler("getuser", getuser))
application.add_handler(CommandHandler("filtergroups", filter_groups))
application.add_handler(CommandHandler("filterchannels", filter_channels))
application.add_handler(CommandHandler("filterusername", filter_username))
application.add_handler(CommandHandler("recentonline", recent_online))
application.add_handler(CommandHandler("statistics", statistics_command))
application.add_handler(CommandHandler("start_broadcast", start_broadcast_command))
application.add_handler(CommandHandler("stop_broadcast", stop_broadcast_command))

# Chạy bot
async def main():
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    try:
        await asyncio.sleep(999999)
    except asyncio.CancelledError:
        await application.updater.stop()
        await application.stop()

if __name__ == "__main__":
    asyncio.run(main())
