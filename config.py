import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))  # ID admin
DELAY = int(os.getenv("DELAY", 2))  # Độ trễ giữa tin nhắn
LOG_FILE = "forward_log.txt"  # File lưu log
BOT_STATUS = {"running": True}  # Trạng thái bot
