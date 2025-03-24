import logging
import asyncio
import re
import os
import sqlite3
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import UserStatusOnline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth, User, Chat, Channel
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Cấu hình logging
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Thông tin bot
BOT_TOKEN = "7695124221:AAGhrm4zaIeMwtipSPqa_44Pq4gw9ZF4668"
API_ID = "24090485"
API_HASH = "b056e6499bc0d4a81ab375773ac1170c"
ADMIN_IDS = [6383614933]

# Khởi tạo bot và scheduler
application = Application.builder().token(BOT_TOKEN).build()
scheduler = AsyncIOScheduler()
scheduler.start()

# Biến toàn cục
clients = {}  # {chat_id: client}
user_data = {}  # {chat_id: {phone, source, target, cleaners, latest_message, spammed_contacts, ...}}

# Class quản lý cơ sở dữ liệu SQLite
class Database:
    def __init__(self, db_name="bot_data.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, allowed INTEGER DEFAULT 0)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS forward_rules (chat_id INTEGER, label TEXT, source_chat_ids TEXT, target_chat_ids TEXT, PRIMARY KEY (chat_id, label))")
            self.conn.execute("CREATE TABLE IF NOT EXISTS whitelist (chat_id INTEGER, label TEXT, type TEXT, data TEXT, PRIMARY KEY (chat_id, label))")
            self.conn.execute("CREATE TABLE IF NOT EXISTS statistics (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, data TEXT, timestamp TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS spam_settings (chat_id INTEGER PRIMARY KEY, spam_delay REAL DEFAULT 1.0, spam_replay INTEGER DEFAULT 0, spam_replay_delay REAL DEFAULT 60.0)")

    def save_user(self, user_id, allowed=True):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO users (user_id, allowed) VALUES (?, ?)", (user_id, 1 if allowed else 0))

    def get_allowed_users(self):
        with self.conn:
            cursor = self.conn.execute("SELECT user_id FROM users WHERE allowed = 1")
            return [row[0] for row in cursor.fetchall()]

    def save_setting(self, key, value):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))

    def get_setting(self, key, default=None):
        with self.conn:
            cursor = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            return json.loads(result[0]) if result else default

    def save_forward_rule(self, chat_id, label, source_chat_ids, target_chat_ids):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO forward_rules (chat_id, label, source_chat_ids, target_chat_ids) VALUES (?, ?, ?, ?)",
                              (chat_id, label, json.dumps(source_chat_ids), json.dumps(target_chat_ids)))

    def get_forward_rules(self, chat_id):
        with self.conn:
            cursor = self.conn.execute("SELECT label, source_chat_ids, target_chat_ids FROM forward_rules WHERE chat_id = ?", (chat_id,))
            return {row[0]: {"source_chat_ids": json.loads(row[1]), "target_chat_ids": json.loads(row[2])} for row in cursor.fetchall()}

    def save_whitelist(self, chat_id, label, type_, data):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO whitelist (chat_id, label, type, data) VALUES (?, ?, ?, ?)",
                              (chat_id, label, type_, json.dumps(data)))

    def get_whitelist(self, chat_id):
        with self.conn:
            cursor = self.conn.execute("SELECT label, type, data FROM whitelist WHERE chat_id = ?", (chat_id,))
            return {row[0]: {"type": row[1], "data": json.loads(row[2])} for row in cursor.fetchall()}

    def save_statistic(self, type_, data):
        with self.conn:
            self.conn.execute("INSERT INTO statistics (type, data, timestamp) VALUES (?, ?, ?)",
                              (type_, json.dumps(data), datetime.now().isoformat()))

    def get_statistics(self, type_, start_time, end_time):
        with self.conn:
            cursor = self.conn.execute("SELECT data FROM statistics WHERE type = ? AND timestamp BETWEEN ? AND ?",
                                       (type_, start_time.isoformat(), end_time.isoformat()))
            return [json.loads(row[0]) for row in cursor.fetchall()]

    def save_spam_settings(self, chat_id, spam_delay=None, spam_replay=None, spam_replay_delay=None):
        with self.conn:
            cursor = self.conn.execute("SELECT spam_delay, spam_replay, spam_replay_delay FROM spam_settings WHERE chat_id = ?", (chat_id,))
            result = cursor.fetchone()
            if result:
                current_delay, current_replay, current_replay_delay = result
                spam_delay = spam_delay if spam_delay is not None else current_delay
                spam_replay = spam_replay if spam_replay is not None else current_replay
                spam_replay_delay = spam_replay_delay if spam_replay_delay is not None else current_replay_delay
                self.conn.execute("UPDATE spam_settings SET spam_delay = ?, spam_replay = ?, spam_replay_delay = ? WHERE chat_id = ?",
                                  (spam_delay, spam_replay, spam_replay_delay, chat_id))
            else:
                self.conn.execute("INSERT INTO spam_settings (chat_id, spam_delay, spam_replay, spam_replay_delay) VALUES (?, ?, ?, ?)",
                                  (chat_id, spam_delay or 1.0, spam_replay if spam_replay is not None else 0, spam_replay_delay or 60.0))

    def get_spam_settings(self, chat_id):
        with self.conn:
            cursor = self.conn.execute("SELECT spam_delay, spam_replay, spam_replay_delay FROM spam_settings WHERE chat_id = ?", (chat_id,))
            result = cursor.fetchone()
            if result:
                return {"spam_delay": result[0], "spam_replay": bool(result[1]), "spam_replay_delay": result[2]}
            return {"spam_delay": 1.0, "spam_replay": False, "spam_replay_delay": 60.0}

# Khởi tạo cơ sở dữ liệu
db = Database()

# Kiểm tra quyền
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_allowed_user(user_id: int) -> bool:
    return user_id in db.get_allowed_users() or is_admin(user_id)

# Menu chính
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🔐 Đăng nhập", callback_data="login"),
         InlineKeyboardButton("📥 Thêm nguồn", callback_data="add_source")],
        [InlineKeyboardButton("📤 Thêm đích", callback_data="add_target"),
         InlineKeyboardButton("▶️ Chuyển tiếp", callback_data="start_forward")],
        [InlineKeyboardButton("🚫 Blacklist", callback_data="blacklist"),
         InlineKeyboardButton("✅ Whitelist", callback_data="whitelist")],
        [InlineKeyboardButton("🔄 Thay thế", callback_data="replace"),
         InlineKeyboardButton("📅 Lên lịch", callback_data="schedule")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"),
         InlineKeyboardButton("📊 Thống kê", callback_data="stats")],
        [InlineKeyboardButton("📜 Nhóm/Kênh", callback_data="list_chats"),
         InlineKeyboardButton("🧹 Cleaners", callback_data="cleaners_menu")],
        [InlineKeyboardButton("📋 Forwarding", callback_data="forward_menu"),
         InlineKeyboardButton("👥 Quản lý", callback_data="user_menu")],
        [InlineKeyboardButton("⚙️ Cài đặt", callback_data="settings_menu"),
         InlineKeyboardButton("📂 Lọc", callback_data="filter_menu")],
        [InlineKeyboardButton("📱 Online", callback_data="recent_online"),
         InlineKeyboardButton("📈 Báo cáo", callback_data="statistics")],
        [InlineKeyboardButton("🛠 Commands", callback_data="commands_menu"),
         InlineKeyboardButton("📧 Spam Settings", callback_data="spam_settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Menu phụ cho các lệnh /
def commands_menu():
    keyboard = [
        [InlineKeyboardButton("▶️ /start - Menu chính", callback_data="cmd_start")],
        [InlineKeyboardButton("📋 /forward - Chuyển tiếp", callback_data="cmd_forward")],
        [InlineKeyboardButton("⚙️ /settings - Cài đặt", callback_data="cmd_settings")],
        [InlineKeyboardButton("🚪 /logout - Đăng xuất", callback_data="cmd_logout")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back")]
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
         InlineKeyboardButton(f"{'✅' if cleaners['photo'] else '🚫'} Photo", callback_data="toggle_cleaner_photo")],
        [InlineKeyboardButton(f"{'✅' if cleaners['url'] else '🚫'} URL", callback_data="toggle_cleaner_url"),
         InlineKeyboardButton(f"{'✅' if cleaners['emoji'] else '🚫'} Emoji", callback_data="toggle_cleaner_emoji")],
        [InlineKeyboardButton("❓ Hướng dẫn", callback_data="cleaners_help"),
         InlineKeyboardButton("🔙 Quay lại", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Menu Spam Settings
def spam_settings_menu(chat_id):
    settings = db.get_spam_settings(chat_id)
    keyboard = [
        [InlineKeyboardButton(f"⏳ Set Delay: {settings['spam_delay']}s", callback_data="set_spam_delay")],
        [InlineKeyboardButton(f"🔁 Replay: {'YES' if settings['spam_replay'] else 'NO'}", callback_data="toggle_spam_replay")],
        [InlineKeyboardButton(f"⏳ Set Delay Replay: {settings['spam_replay_delay']}s", callback_data="set_spam_replay_delay")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Menu Broadcast
def broadcast_menu(chat_id):
    broadcast_enabled = user_data.get(chat_id, {}).get("broadcast_enabled", False)
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast đến nhóm", callback_data="broadcast_groups"),
         InlineKeyboardButton("📢 Broadcast đến danh bạ", callback_data="broadcast_contacts")],
        [InlineKeyboardButton("📢 Broadcast đến tất cả", callback_data="broadcast_all"),
         InlineKeyboardButton("📂 Theo Folder", callback_data="broadcast_folders")],
        [InlineKeyboardButton("📄 Spam theo File", callback_data="broadcast_file"),
         InlineKeyboardButton("🔙 Quay lại", callback_data="back")],
        [InlineKeyboardButton("▶️ Bắt đầu Broadcast" if not broadcast_enabled else "⏹ Kết thúc Broadcast",
                              callback_data="start_broadcast" if not broadcast_enabled else "stop_broadcast")]
    ]
    status = "đang chạy" if broadcast_enabled else "đã dừng"
    return InlineKeyboardMarkup(keyboard)

# Menu Broadcast theo Folder
def broadcast_folders_menu():
    keyboard = [
        [InlineKeyboardButton("📂 All", callback_data="broadcast_folder_all"),
         InlineKeyboardButton("👤 Personal", callback_data="broadcast_folder_personal")],
        [InlineKeyboardButton("👥 Groups", callback_data="broadcast_folder_groups"),
         InlineKeyboardButton("📢 Channels", callback_data="broadcast_folder_channels")],
        [InlineKeyboardButton("🤖 Bots", callback_data="broadcast_folder_bots"),
         InlineKeyboardButton("🔙 Quay lại", callback_data="broadcast_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="back")]])

# Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    await update.message.reply_text("Chào mừng bạn! Chọn hành động:", reply_markup=main_menu())

# Xử lý nút
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if not is_allowed_user(user_id):
        await query.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return

    # Khởi tạo user_data nếu chưa có
    if chat_id not in user_data:
        user_data[chat_id] = {
            "latest_message": None,
            "spammed_contacts": set(),
            "phone_numbers_from_file": [],
            "current_phone_index": 0
        }
    if "cleaners" not in user_data[chat_id]:
        user_data[chat_id]["cleaners"] = {
            "text": False, "audio": False, "url": False, "url_preview": False,
            "video": False, "sticker": False, "hashtag": False, "mention": False,
            "photo": False, "document": False, "video_note": False, "voice": False,
            "emoji": False, "dice": False, "photo_with_text": False, "animation": False
        }

    if query.data == "login":
        await query.edit_message_text(text="Gửi số điện thoại (ví dụ: +84123456789):", reply_markup=back_button())
        context.user_data["state"] = "waiting_phone"

    elif query.data == "add_source":
        await query.edit_message_text(text="Gửi user_id của kênh/nhóm nguồn (ví dụ: -100123456789):", reply_markup=back_button())
        context.user_data["state"] = "waiting_source"

    elif query.data == "add_target":
        await query.edit_message_text(text="Gửi user_id của kênh/nhóm đích (ví dụ: -100987654321):", reply_markup=back_button())
        context.user_data["state"] = "waiting_target"

    elif query.data == "start_forward":
        if chat_id not in clients:
            await query.edit_message_text(text="Vui lòng đăng nhập trước!", reply_markup=main_menu())
        elif "source" not in user_data.get(chat_id, {}) or "target" not in user_data.get(chat_id, {}):
            await query.edit_message_text(text="Vui lòng thêm nguồn và đích trước!", reply_markup=main_menu())
        else:
            await query.edit_message_text(text="▶️ Đã bắt đầu chuyển tiếp!", reply_markup=main_menu())
            setup_forwarding(chat_id)

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
            [InlineKeyboardButton("🔙 Quay lại", callback_data="back")]
        ]
        await query.edit_message_text(text="🔄 Chọn loại thay thế:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "replace_text":
        await query.edit_message_text(text="📝 Nhập cặp từ thay thế (ví dụ: hello=>hi):", reply_markup=back_button())
        context.user_data["state"] = "waiting_replace_text"

    elif query.data == "replace_emoji":
        await query.edit_message_text(text="😊 Nhập cặp emoji thay thế (ví dụ: 😊=>😄):", reply_markup=back_button())
        context.user_data["state"] = "waiting_replace_emoji"

    elif query.data == "schedule":
        await query.edit_message_text(text="⏰ Nhập thời gian và nội dung (ví dụ: 1m Tin nhắn tự động):", reply_markup=back_button())
        context.user_data["state"] = "waiting_schedule"

    elif query.data == "broadcast_menu":
        await query.edit_message_text(
            text=f"📢 Chọn loại broadcast (Trạng thái: {'đang chạy' if user_data.get(chat_id, {}).get('broadcast_enabled', False) else 'đã dừng'}):",
            reply_markup=broadcast_menu(chat_id)
        )

    elif query.data == "broadcast_groups":
        user_data[chat_id]["broadcast_target"] = "groups"
        await query.edit_message_text(text="📢 Nhập nội dung broadcast đến các nhóm:", reply_markup=back_button())
        context.user_data["state"] = "waiting_broadcast_groups"

    elif query.data == "broadcast_contacts":
        user_data[chat_id]["broadcast_target"] = "contacts"
        await query.edit_message_text(text="📢 Nhập nội dung broadcast đến danh bạ:", reply_markup=back_button())
        context.user_data["state"] = "waiting_broadcast_contacts"

    elif query.data == "broadcast_all":
        user_data[chat_id]["broadcast_target"] = "all"
        await query.edit_message_text(text="📢 Nhập nội dung broadcast đến tất cả:", reply_markup=back_button())
        context.user_data["state"] = "waiting_broadcast_all"

    elif query.data == "broadcast_folders":
        await query.edit_message_text(
            text="📂 Chọn folder để broadcast:",
            reply_markup=broadcast_folders_menu()
        )

    elif query.data.startswith("broadcast_folder_"):
        folder_type = query.data.split("_")[-1]
        user_data[chat_id]["broadcast_target"] = f"folder_{folder_type}"
        await query.edit_message_text(
            text=f"📢 Nhập nội dung broadcast đến folder {folder_type.capitalize()}:",
            reply_markup=back_button()
        )
        context.user_data["state"] = f"waiting_broadcast_folder_{folder_type}"

    elif query.data == "broadcast_file":
        await query.edit_message_text(
            text="📄 Vui lòng gửi file .txt chứa danh sách số điện thoại (mỗi số trên một dòng):",
            reply_markup=back_button()
        )
        context.user_data["state"] = "waiting_broadcast_file"

    elif query.data == "start_broadcast":
        if chat_id not in clients:
            await query.edit_message_text(text="Vui lòng đăng nhập trước!", reply_markup=main_menu())
        elif "source" not in user_data.get(chat_id, {}):
            await query.edit_message_text(text="Vui lòng thêm nguồn trước!", reply_markup=main_menu())
        elif "broadcast_target" not in user_data.get(chat_id, {}):
            await query.edit_message_text(text="Vui lòng chọn loại broadcast trước!", reply_markup=main_menu())
        else:
            user_data[chat_id]["broadcast_enabled"] = True
            setup_broadcast(chat_id)
            await query.edit_message_text(text="▶️ Đã bắt đầu broadcast!", reply_markup=main_menu())

    elif query.data == "stop_broadcast":
        user_data[chat_id]["broadcast_enabled"] = False
        await query.edit_message_text(text="⏹ Đã kết thúc broadcast!", reply_markup=main_menu())

    elif query.data == "cleaners_menu":
        await query.edit_message_text(text="🧹 Cleaners Menu 🧹\n\nToggle để lọc nội dung:", reply_markup=cleaners_menu(chat_id))

    elif query.data.startswith("toggle_cleaner_"):
        cleaner_type = query.data.replace("toggle_cleaner_", "")
        user_data[chat_id]["cleaners"][cleaner_type] = not user_data[chat_id]["cleaners"][cleaner_type]
        await query.edit_message_text(text="🧹 Cleaners Menu 🧹\n\nToggle để lọc nội dung:", reply_markup=cleaners_menu(chat_id))

    elif query.data == "cleaners_help":
        await query.edit_message_text(
            text="❓ Hướng dẫn Cleaners ❓\n\n"
                 "Cleaners giúp lọc nội dung tin nhắn:\n"
                 "- ✅: Loại bỏ nội dung (Text, Photo, URL, Emoji).\n"
                 "- 🚫: Cho phép nội dung.\n\n"
                 "Ví dụ:\n- 'Text' ✅: Xóa toàn bộ văn bản.\n- 'Photo' ✅: Bỏ qua ảnh.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Quay lại", callback_data="cleaners_menu")]])
        )

    elif query.data == "stats":
        await statistics_command(query.message, context)

    elif query.data == "list_chats":
        if chat_id not in clients:
            await query.edit_message_text(text="Vui lòng đăng nhập trước!", reply_markup=main_menu())
            return
        chats = []
        async for dialog in clients[chat_id].iter_dialogs():
            username = dialog.entity.username if hasattr(dialog.entity, "username") and dialog.entity.username else "Không có"
            chats.append(f"{dialog.name} (@{username}) - ID: {dialog.entity.id}")
        text = "📜 Danh sách nhóm/kênh:\n" + "\n".join(chats) if chats else "Không tìm thấy nhóm/kênh nào!"
        await query.edit_message_text(text=text, reply_markup=back_button())

    elif query.data == "forward_menu":
        keyboard = [
            [InlineKeyboardButton("Xóa tất cả", callback_data="forward_clear"),
             InlineKeyboardButton("Hiển thị", callback_data="forward_show")]
        ]
        await query.edit_message_text("📋 Forwarding Menu 📋\n\n"
                                      "Cú pháp: /forward add LABEL SOURCE -> TARGET\n"
                                      "Ví dụ: /forward add work1 2222 -> 66666", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "forward_clear":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể xóa quy tắc forward!", reply_markup=main_menu())
            return
        db.get_forward_rules(chat_id).clear()
        await query.edit_message_text("Đã xóa tất cả quy tắc forward.", reply_markup=main_menu())

    elif query.data == "forward_show":
        rules = db.get_forward_rules(chat_id)
        if not rules:
            await query.edit_message_text("Không có quy tắc forward nào.", reply_markup=main_menu())
            return
        response = "📋 Quy tắc forward:\n\n"
        for label, rule in rules.items():
            response += f"🔹 {label}: {rule['source_chat_ids']} -> {rule['target_chat_ids']}\n"
        await query.edit_message_text(response, reply_markup=back_button())

    elif query.data == "user_menu":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể quản lý người dùng!", reply_markup=main_menu())
            return
        await query.edit_message_text("📋 Quản lý người dùng 📋\n\n"
                                      "/user add USER_ID\n/user remove USER_ID\n/user list", reply_markup=back_button())

    elif query.data == "settings_menu":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings = db.get_setting("settings", {"forward_enabled": True, "whitelist_enabled": True, "forward_mode": "forward"})
        keyboard = [
            [InlineKeyboardButton("Forward: " + ("ON" if settings["forward_enabled"] else "OFF"), callback_data="toggle_forward")],
            [InlineKeyboardButton("Whitelist: " + ("ON" if settings["whitelist_enabled"] else "OFF"), callback_data="toggle_whitelist")],
            [InlineKeyboardButton("Mode: " + ("Forward" if settings["forward_mode"] == "forward" else "Copy"), callback_data="toggle_forward_mode")],
            [InlineKeyboardButton("Quay lại", callback_data="back")]
        ]
        await query.edit_message_text(f"⚙️ Cài đặt ⚙️\n\n"
                                      f"Forwarding: {'Enabled' if settings['forward_enabled'] else 'Disabled'}\n"
                                      f"Whitelist: {'Enabled' if settings['whitelist_enabled'] else 'Disabled'}\n"
                                      f"Mode: {settings['forward_mode'].capitalize()}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "toggle_forward":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings = db.get_setting("settings", {"forward_enabled": True, "whitelist_enabled": True, "forward_mode": "forward"})
        settings["forward_enabled"] = not settings["forward_enabled"]
        db.save_setting("settings", settings)
        await query.edit_message_text(f"Forwarding đã được {'bật' if settings['forward_enabled'] else 'tắt'}.", reply_markup=main_menu())

    elif query.data == "toggle_whitelist":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings = db.get_setting("settings", {"forward_enabled": True, "whitelist_enabled": True, "forward_mode": "forward"})
        settings["whitelist_enabled"] = not settings["whitelist_enabled"]
        db.save_setting("settings", settings)
        await query.edit_message_text(f"Whitelist đã được {'bật' if settings['whitelist_enabled'] else 'tắt'}.", reply_markup=main_menu())

    elif query.data == "toggle_forward_mode":
        if not is_admin(user_id):
            await query.edit_message_text(text="Chỉ admin mới có thể thay đổi cài đặt!", reply_markup=main_menu())
            return
        settings = db.get_setting("settings", {"forward_enabled": True, "whitelist_enabled": True, "forward_mode": "forward"})
        settings["forward_mode"] = "copy" if settings["forward_mode"] == "forward" else "forward"
        db.save_setting("settings", settings)
        await query.edit_message_text(f"Mode đã được chuyển thành {'Copy' if settings['forward_mode'] == 'copy' else 'Forward'}.", reply_markup=main_menu())

    elif query.data == "filter_menu":
        await query.edit_message_text("📂 Lọc 📂\n\n"
                                      "/filtergroups - Lọc nhóm\n"
                                      "/filterchannels - Lọc kênh\n"
                                      "/filterusername USERNAME - Tìm username", reply_markup=back_button())

    elif query.data == "recent_online":
        await recent_online(query.message, context)

    elif query.data == "statistics":
        await statistics_command(query.message, context)

    elif query.data == "commands_menu":
        await query.edit_message_text(text="🛠 Chọn lệnh:", reply_markup=commands_menu())

    elif query.data.startswith("cmd_"):
        cmd = query.data.split("_")[1]
        if cmd == "start":
            await query.edit_message_text(text="▶️ Đã chọn /start.", reply_markup=main_menu())
        elif cmd == "forward":
            await query.edit_message_text(text="📋 Đã chọn /forward. Cấu hình chuyển tiếp.", reply_markup=back_button())
        elif cmd == "settings":
            await query.edit_message_text(text="⚙️ Đã chọn /settings. Điều chỉnh cài đặt.", reply_markup=back_button())
        elif cmd == "logout":
            if chat_id in clients:
                await clients[chat_id].disconnect()
                del clients[chat_id]
                session_file = f"sessions/{chat_id}_{user_data[chat_id]['phone']}.session"
                if os.path.exists(session_file):
                    os.remove(session_file)
                await query.edit_message_text("🚪 Đã đăng xuất và xóa session.", reply_markup=main_menu())
            else:
                await query.edit_message_text("Bạn chưa đăng nhập.", reply_markup=main_menu())

    elif query.data == "spam_settings_menu":
        await query.edit_message_text(
            text="📧 Spam Settings 📧\n\n"
                 "Cài đặt thời gian gửi tin nhắn spam và chế độ lặp lại.",
            reply_markup=spam_settings_menu(chat_id)
        )

    elif query.data == "set_spam_delay":
        await query.edit_message_text(
            text="⏳ Nhập thời gian trễ giữa các tin nhắn spam (giây, ví dụ: 5.5):",
            reply_markup=back_button()
        )
        context.user_data["state"] = "waiting_spam_delay"

    elif query.data == "toggle_spam_replay":
        settings = db.get_spam_settings(chat_id)
        settings["spam_replay"] = not settings["spam_replay"]
        db.save_spam_settings(chat_id, spam_replay=settings["spam_replay"])
        await query.edit_message_text(
            text="📧 Spam Settings 📧\n\n"
                 "Cài đặt thời gian gửi tin nhắn spam và chế độ lặp lại.",
            reply_markup=spam_settings_menu(chat_id)
        )

    elif query.data == "set_spam_replay_delay":
        await query.edit_message_text(
            text="⏳ Nhập thời gian trễ giữa các chu kỳ lặp lại (giây, ví dụ: 60):",
            reply_markup=back_button()
        )
        context.user_data["state"] = "waiting_spam_replay_delay"

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

    user_data[chat_id] = user_data.get(chat_id, {
        "latest_message": None,
        "spammed_contacts": set(),
        "phone_numbers_from_file": [],
        "current_phone_index": 0
    })
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
            setup_broadcast(chat_id)
            await update.message.reply_text("Đã đăng nhập thành công từ phiên trước!", reply_markup=main_menu())
            context.user_data["state"] = None

    elif state == "waiting_code":
        client = context.user_data["client"]
        try:
            await client.sign_in(code=text)
            clients[chat_id] = client
            setup_forwarding(chat_id)
            setup_broadcast(chat_id)
            await update.message.reply_text("Đăng nhập thành công!", reply_markup=main_menu())
        except SessionPasswordNeededError:
            await update.message.reply_text("Tài khoản yêu cầu mật khẩu 2FA. Nhập mật khẩu:", reply_markup=back_button())
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
            setup_broadcast(chat_id)
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
            await update.message.reply_text("📢 Đã gửi broadcast đến các nhóm!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_broadcast_contacts":
        if chat_id in clients:
            await broadcast_message(clients[chat_id], message, target="contacts")
            await update.message.reply_text("📢 Đã gửi broadcast đến danh bạ!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_broadcast_all":
        if chat_id in clients:
            await broadcast_message(clients[chat_id], message, target="all")
            await update.message.reply_text("📢 Đã gửi broadcast đến tất cả!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state.startswith("waiting_broadcast_folder_"):
        folder_type = state.split("_")[-1]
        if chat_id in clients:
            await broadcast_message(clients[chat_id], message, target=f"folder_{folder_type}")
            await update.message.reply_text(f"📢 Đã gửi broadcast đến folder {folder_type.capitalize()}!", reply_markup=main_menu())
        else:
            await update.message.reply_text("Vui lòng đăng nhập trước!", reply_markup=main_menu())
        context.user_data["state"] = None

    elif state == "waiting_broadcast_file":
        if not message.document or not message.document.file_name.endswith(".txt"):
            await update.message.reply_text("Vui lòng gửi file .txt chứa danh sách số điện thoại!", reply_markup=back_button())
            return
        file = await message.document.get_file()
        file_path = f"temp_{chat_id}.txt"
        await file.download_to_drive(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            phone_numbers = [line.strip() for line in f.readlines() if line.strip()]
        user_data[chat_id]["phone_numbers_from_file"] = phone_numbers
        user_data[chat_id]["current_phone_index"] = 0
        user_data[chat_id]["broadcast_target"] = "file"
        os.remove(file_path)
        await update.message.reply_text(f"📄 Đã tải lên danh sách {len(phone_numbers)} số điện thoại. Bắt đầu broadcast?", reply_markup=broadcast_menu(chat_id))
        context.user_data["state"] = None

    elif state == "waiting_spam_delay":
        try:
            delay = float(text)
            if delay <= 0:
                raise ValueError("Thời gian trễ phải lớn hơn 0!")
            db.save_spam_settings(chat_id, spam_delay=delay)
            await update.message.reply_text(f"⏳ Đã đặt thời gian trễ spam: {delay} giây", reply_markup=spam_settings_menu(chat_id))
        except ValueError as e:
            await update.message.reply_text(f"Lỗi: {str(e)}. Vui lòng nhập lại (ví dụ: 5.5).", reply_markup=back_button())
        context.user_data["state"] = None

    elif state == "waiting_spam_replay_delay":
        try:
            delay = float(text)
            if delay <= 0:
                raise ValueError("Thời gian trễ phải lớn hơn 0!")
            db.save_spam_settings(chat_id, spam_replay_delay=delay)
            await update.message.reply_text(f"⏳ Đã đặt thời gian trễ lặp lại: {delay} giây", reply_markup=spam_settings_menu(chat_id))
        except ValueError as e:
            await update.message.reply_text(f"Lỗi: {str(e)}. Vui lòng nhập lại (ví dụ: 60).", reply_markup=back_button())
        context.user_data["state"] = None

# Lệnh /start_broadcast
async def start_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return
    if "source" not in user_data.get(chat_id, {}):
        await update.message.reply_text("Vui lòng thêm nguồn trước!")
        return
    if "broadcast_target" not in user_data.get(chat_id, {}):
        await update.message.reply_text("Vui lòng chọn loại broadcast trước!")
        return
    user_data[chat_id]["broadcast_enabled"] = True
    setup_broadcast(chat_id)
    await update.message.reply_text("▶️ Đã bắt đầu broadcast!")

# Lệnh /stop_broadcast
async def stop_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    user_data[chat_id]["broadcast_enabled"] = False
    await update.message.reply_text("⏹ Đã kết thúc broadcast!")

# Lệnh /forward
async def forward_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_admin(user_id):
        await update.message.reply_text("Chỉ admin mới có thể cấu hình forward!")
        return

    if not context.args or len(context.args) < 3:
        keyboard = [
            [InlineKeyboardButton("Xóa tất cả", callback_data="forward_clear"),
             InlineKeyboardButton("Hiển thị", callback_data="forward_show")]
        ]
        await update.message.reply_text("📋 Forwarding Menu 📋\n\n"
                                        "Cú pháp: /forward add LABEL SOURCE -> TARGET\n"
                                        "Ví dụ: /forward add work1 2222 -> 66666", reply_markup=InlineKeyboardMarkup(keyboard))
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
                await update.message.reply_text("Cú pháp không hợp lệ! Sử dụng: /forward add LABEL SOURCE -> TARGET")
                return
            source_part, target_part = command_text.split("->")
            source_chat_ids = [int(chat_id.strip()) for chat_id in source_part.split(",") if chat_id.strip()]
            target_chat_ids = [int(chat_id.strip()) for chat_id in target_part.split(",") if chat_id.strip()]
            if not source_chat_ids or not target_chat_ids:
                await update.message.reply_text("Vui lòng cung cấp SOURCE và TARGET hợp lệ!")
                return
            if not re.match(r'^[a-zA-Z0-9_]+$', label):
                await update.message.reply_text("LABEL không được chứa khoảng trắng hoặc ký tự đặc biệt!")
                return
            db.save_forward_rule(chat_id, label, source_chat_ids, target_chat_ids)
            await update.message.reply_text(f"Đã thêm quy tắc forward với label '{label}'.")

        elif action == "remove":
            rules = db.get_forward_rules(chat_id)
            if label in rules:
                del rules[label]
                db.save_forward_rule(chat_id, label, [], [])
                await update.message.reply_text(f"Đã xóa quy tắc forward với label '{label}'.")
            else:
                await update.message.reply_text(f"Không tìm thấy quy tắc forward với label '{label}'.")

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Lệnh /whitelist
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
                                        "✅ Basic Examples:\n"
                                        "➡️ /whitelist add label1 copyright\n"
                                        "➡️ /whitelist add label1 copyright,DMCA\n\n"
                                        "✅ Advanced Examples:\n"
                                        "➡️ /whitelist add label1_regex (black|white)\n"
                                        "➡️ /whitelist add group1_user zinREAL,410995490")
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
            if label.endswith("_regex"):
                db.save_whitelist(chat_id, label, "regex", items)
            elif label.endswith("_user"):
                user_list = [item.strip() for item in items.split(",")]
                db.save_whitelist(chat_id, label, "user", user_list)
            else:
                word_list = [word.strip() for word in items.split(",")]
                db.save_whitelist(chat_id, label, "word", word_list)
            await update.message.reply_text(f"Đã thêm whitelist với label '{label}'.")

        elif action == "remove":
            whitelist = db.get_whitelist(chat_id)
            if label in whitelist:
                del whitelist[label]
                db.save_whitelist(chat_id, label, "", [])
                await update.message.reply_text(f"Đã xóa whitelist với label '{label}'.")
            else:
                await update.message.reply_text(f"Không tìm thấy whitelist với label '{label}'.")

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Lệnh /user
async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Chỉ admin mới có thể quản lý người dùng!")
        return

    if not context.args:
        await update.message.reply_text("📋 Quản lý người dùng 📋\n\n"
                                        "/user add USER_ID\n/user remove USER_ID\n/user list")
        return

    try:
        action = context.args[0].lower()
        if action == "add":
            new_user_id = int(context.args[1])
            if new_user_id not in db.get_allowed_users():
                db.save_user(new_user_id, True)
                await update.message.reply_text(f"Đã thêm người dùng {new_user_id}.")
            else:
                await update.message.reply_text(f"Người dùng {new_user_id} đã có trong danh sách.")

        elif action == "remove":
            user_id_to_remove = int(context.args[1])
            if user_id_to_remove in db.get_allowed_users():
                db.save_user(user_id_to_remove, False)
                await update.message.reply_text(f"Đã xóa người dùng {user_id_to_remove}.")
            else:
                await update.message.reply_text(f"Không tìm thấy người dùng {user_id_to_remove}.")

        elif action == "list":
            users = db.get_allowed_users()
            if not users:
                await update.message.reply_text("Không có người dùng nào được phép.")
                return
            response = "📋 Danh sách người dùng:\n\n"
            for user_id in users:
                response += f"🔹 {user_id}\n"
            await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Lỗi: {str(e)}")

# Lệnh /getchatid, /getgroup, /getuser
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
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return
    dialogs = await clients[chat_id].get_dialogs()
    response = "📋 Danh sách tất cả nhóm, kênh, và người dùng:\n\n"
    for dialog in dialogs:
        entity = dialog.entity
        if isinstance(entity, User):
            name = f"{entity.first_name} {entity.last_name or ''}".strip()
            username = entity.username or "N/A"
            response += f"👤 {name} (ID: {entity.id}, Username: @{username})\n"
        elif isinstance(entity, Chat):
            response += f"👥 {entity.title} (ID: {entity.id})\n"
        elif isinstance(entity, Channel):
            username = entity.username or "N/A"
            response += f"📢 {entity.title} (ID: {entity.id}, Username: @{username})\n"
    await update.message.reply_text(response)

# Lệnh /filtergroups
async def filter_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return
    dialogs = await clients[chat_id].get_dialogs()
    groups = [d for d in dialogs if d.is_group]
    if not groups:
        await update.message.reply_text("Không tìm thấy nhóm nào!")
        return
    response = "📋 Danh sách nhóm:\n\n"
    for group in groups:
        response += f"🔹 {group.title} (ID: {group.id})\n"
    await update.message.reply_text(response)

# Lệnh /filterchannels
async def filter_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return
    dialogs = await clients[chat_id].get_dialogs()
    channels = [d for d in dialogs if d.is_channel]
    if not channels:
        await update.message.reply_text("Không tìm thấy kênh nào!")
        return
    response = "📋 Danh sách kênh:\n\n"
    for channel in channels:
        response += f"🔹 {channel.title} (ID: {channel.id})\n"
    await update.message.reply_text(response)

# Lệnh /filterusername
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
    entity = await clients[chat_id].get_entity(username)
    response = "📋 Kết quả tìm kiếm:\n\n"
    if hasattr(entity, 'title'):
        response += f"🔹 {entity.title} (ID: {entity.id}, Type: {'Channel' if entity.broadcast else 'Group'})\n"
    else:
        response += f"🔹 {entity.first_name} {entity.last_name or ''} (ID: {entity.id}, Type: User, Username: @{entity.username})\n"
    await update.message.reply_text(response)

# Lệnh /recentonline
async def recent_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    if chat_id not in clients:
        await update.message.reply_text("Vui lòng đăng nhập trước!")
        return
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
        await update.message.reply_text("Không có người dùng nào online gần đây!")
        return
    online_users.sort(key=lambda x: ["Online", "Recently Online", "Last Week", "Last Month"].index(x[1]))
    response = "📋 Danh sách người dùng online gần nhất:\n\n"
    for user, status in online_users[:10]:
        response += f"🔹 {user.first_name} {user.last_name or ''} (@{user.username or 'N/A'}) - {status}\n"
        db.save_statistic("online_user", {"user_id": user.id, "username": user.username, "status": status})
    await update.message.reply_text(response)

# Lệnh /statistics
async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed_user(user_id):
        await update.message.reply_text("Bạn không có quyền sử dụng bot này!")
        return
    start_time = datetime(2025, 3, 22, 0, 0, 0)
    end_time = datetime.now()
    forwarded_msgs = db.get_statistics("forwarded_message", start_time, end_time)
    online_users = db.get_statistics("online_user", start_time, end_time)
    response = "📊 Thống kê từ 00:00 22/03/2025 đến hiện tại 📊\n\n"
    response += f"Số tin nhắn đã chuyển tiếp: {len(forwarded_msgs)}\n"
    response += f"Số người dùng online (đã kiểm tra): {len(online_users)}\n"
    await update.reply_text(response)

# Hàm thay thế nội dung
def replace_content(chat_id, text):
    replace_dict = user_data.get(chat_id, {}).get("replace_dict", {})
    emoji_replace = user_data.get(chat_id, {}).get("emoji_replace", {})
    for key, value in replace_dict.items():
        text = re.sub(r'\b' + key + r'\b', value, text, flags=re.IGNORECASE)
    for emoji, replacement in emoji_replace.items():
        text = text.replace(emoji, replacement)
    return text

# Hàm lọc nội dung
def apply_cleaners(chat_id, message):
    cleaners = user_data.get(chat_id, {}).get("cleaners", {
        "text": False, "audio": False, "url": False, "url_preview": False,
        "video": False, "sticker": False, "hashtag": False, "mention": False,
        "photo": False, "document": False, "video_note": False, "voice": False,
        "emoji": False, "dice": False, "photo_with_text": False, "animation": False
    })
    msg_text = message.text or ""
    should_forward = True

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

    if not should_forward and not msg_text:
        return None, None
    message.text = msg_text
    return message, should_forward

# Hàm lên lịch gửi tin nhắn
async def scheduled_message(client, target, message):
    try:
        await client.send_message(target, message)
        logger.info(f"Đã gửi tin nhắn tự động đến {target}: {message}")
    except Exception as e:
        logger.error(f"Lỗi khi gửi tin nhắn tự động: {str(e)}")

# Hàm spam tin nhắn
async def spam_message(client, target, chat_id):
    settings = db.get_spam_settings(chat_id)
    spam_delay = settings["spam_delay"]
    spam_replay = settings["spam_replay"]
    spam_replay_delay = settings["spam_replay_delay"]

    # Lấy tin nhắn mới nhất từ nguồn
    message = user_data[chat_id]["latest_message"]
    if not message:
        logger.warning(f"Không có tin nhắn mới nhất để spam cho chat_id {chat_id}")
        return

    message, should_forward = apply_cleaners(chat_id, message)
    if not should_forward or message is None:
        return

    while True:
        try:
            if message.media:
                await client.send_file(target, message.media, caption=message.text or "")
            else:
                await client.send_message(target, message.text or "Spam message")
            logger.info(f"Đã gửi tin nhắn spam đến {target}: {message.text}")
            db.save_statistic("forwarded_message", {"to_chat_id": target, "message": message.text})
            await asyncio.sleep(spam_delay)
            if not spam_replay:
                break
            await asyncio.sleep(spam_replay_delay - spam_delay)
        except Exception as e:
            logger.error(f"Lỗi khi gửi tin nhắn spam: {str(e)}")
            break

# Hàm broadcast
async def broadcast_message(client, message, target="all"):
    chat_id = list(clients.keys())[list(clients.values()).index(client)]
    message, should_forward = apply_cleaners(chat_id, message)
    if not should_forward or message is None:
        return

    # Lưu tin nhắn mới nhất để dùng cho spam
    user_data[chat_id]["latest_message"] = message

    if target.startswith("folder_"):
        folder_type = target.split("_")[-1]
        async for dialog in client.iter_dialogs():
            should_send = False
            if folder_type == "all":
                should_send = True
            elif folder_type == "personal" and dialog.is_user and not dialog.entity.bot:
                should_send = True
            elif folder_type == "groups" and dialog.is_group:
                should_send = True
            elif folder_type == "channels" and dialog.is_channel:
                should_send = True
            elif folder_type == "bots" and dialog.is_user and dialog.entity.bot:
                should_send = True
            if should_send:
                scheduler.add_job(spam_message, 'interval', seconds=1, args=[client, dialog.entity.id, chat_id])
                await asyncio.sleep(1)

    elif target == "contacts":
        contacts = await client.get_contacts()
        if not contacts:
            logger.info("Danh bạ trống!")
            return
        contact_ids = [contact.id for contact in contacts]
        spammed_contacts = user_data[chat_id]["spammed_contacts"]
        
        # Lọc các liên hệ chưa được spam
        remaining_contacts = [cid for cid in contact_ids if cid not in spammed_contacts]
        
        # Nếu đã spam hết, reset và bắt đầu lại
        if not remaining_contacts:
            user_data[chat_id]["spammed_contacts"].clear()
            remaining_contacts = contact_ids
        
        for contact_id in remaining_contacts:
            try:
                scheduler.add_job(spam_message, 'interval', seconds=1, args=[client, contact_id, chat_id])
                user_data[chat_id]["spammed_contacts"].add(contact_id)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Lỗi khi gửi broadcast đến contact {contact_id}: {str(e)}")

    elif target == "file":
        phone_numbers = user_data[chat_id]["phone_numbers_from_file"]
        if not phone_numbers:
            logger.info("Không có số điện thoại để spam!")
            return
        current_index = user_data[chat_id]["current_phone_index"]
        phone_number = phone_numbers[current_index]
        try:
            entity = await client.get_entity(phone_number)
            scheduler.add_job(spam_message, 'interval', seconds=1, args=[client, entity.id, chat_id])
            logger.info(f"Đã gửi broadcast đến số {phone_number}")
        except Exception as e:
            logger.error(f"Lỗi khi gửi broadcast đến số {phone_number}: {str(e)}")
        
        # Cập nhật chỉ số, quay lại từ đầu nếu đã spam hết
        current_index = (current_index + 1) % len(phone_numbers)
        user_data[chat_id]["current_phone_index"] = current_index

    else:  # Target là "all" hoặc "groups"
        sent_to = set()
        async for dialog in client.iter_dialogs():
            should_send = (target == "all" and (dialog.is_group or dialog.is_user)) or \
                          (target == "groups" and dialog.is_group)
            if should_send and dialog.entity.id not in sent_to:
                try:
                    scheduler.add_job(spam_message, 'interval', seconds=1, args=[client, dialog.entity.id, chat_id])
                    sent_to.add(dialog.entity.id)
                    logger.info(f"Đã gửi broadcast đến {dialog.name}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Lỗi khi gửi broadcast đến {dialog.name}: {str(e)}")

# Hàm kiểm tra whitelist
def check_whitelist(chat_id, message_text: str, sender: dict) -> bool:
    settings = db.get_setting("settings", {"whitelist_enabled": True})
    if not settings["whitelist_enabled"]:
        return True
    whitelist = db.get_whitelist(chat_id)
    if not whitelist:
        return True

    for label, config in whitelist.items():
        if config["type"] == "word":
            for word in config["data"]:
                if word in message_text:
                    logger.info(f"Tin nhắn khớp với whitelist '{label}' (word: {word})")
                    return True
        elif config["type"] == "regex":
            pattern = config["data"].replace("==OR==", "|").replace("==AND==", ".*")
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
            for user in config["data"]:
                if user == sender_id or (sender_username and user.lower() == sender_username.lower()):
                    logger.info(f"Tin nhắn khớp với whitelist '{label}' (user: {user})")
                    return True
    logger.info("Tin nhắn không khớp với whitelist, bỏ qua.")
    return False

# Thiết lập chuyển tiếp
def setup_forwarding(chat_id):
    if chat_id not in clients:
        return
    client = clients[chat_id]
    settings = db.get_setting("settings", {"forward_enabled": True})
    if not settings["forward_enabled"]:
        return

    @client.on(events.NewMessage())
    async def handler(event):
        settings = db.get_setting("settings", {"forward_enabled": True})
        if not settings["forward_enabled"]:
            return
        message_text = event.message.text or ""
        sender = await event.get_sender()
        sender_info = {"id": sender.id if sender else None, "username": sender.username if sender and hasattr(sender, "username") else None}
        chat_id_event = event.chat_id
        rules = db.get_forward_rules(chat_id)
        target_chat_ids = [chat_id for label, rule in rules.items() if chat_id_event in rule["source_chat_ids"] for chat_id in rule["target_chat_ids"]]
        
        # Lưu tin nhắn mới nhất từ nguồn
        if chat_id_event in [rule["source_chat_ids"][0] for rule in rules.values() if rule["source_chat_ids"]]:
            user_data[chat_id]["latest_message"] = event.message

        if target_chat_ids and check_whitelist(chat_id, message_text, sender_info):
            message, should_forward = apply_cleaners(chat_id, event.message)
            if not should_forward or message is None:
                return
            for target_chat_id in target_chat_ids:
                scheduler.add_job(spam_message, 'interval', seconds=1, args=[client, target_chat_id, chat_id])

# Thiết lập broadcast
def setup_broadcast(chat_id):
    if chat_id not in clients or not user_data.get(chat_id, {}).get("broadcast_enabled", False):
        return
    client = clients[chat_id]
    source = user_data[chat_id]["source"]

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        if not user_data[chat_id].get("broadcast_enabled", False):
            return
        message_text = event.message.text or ""
        sender = await event.get_sender()
        sender_info = {"id": sender.id if sender else None, "username": sender.username if sender and hasattr(sender, "username") else None}
        if check_whitelist(chat_id, message_text, sender_info):
            user_data[chat_id]["latest_message"] = event.message  # Lưu tin nhắn mới nhất
            target = user_data[chat_id]["broadcast_target"]
            if target == "file":
                await broadcast_message(client, event.message, target="file")
            else:
                await broadcast_message(client, event.message, target=target)

# Đăng ký lệnh
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
    await asyncio.sleep(999999)

if __name__ == "__main__":
    asyncio.run(main())
