
from dotenv import load_dotenv
import os

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "session")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))
SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID"))
TARGET_CHAT_IDS = list(map(int, os.getenv("TARGET_CHAT_IDS").split(",")))
FLASK_PASSWORD = os.getenv("FLASK_PASSWORD")

_status_path = ".status"

def ENABLE_FORWARD():
    return os.path.exists(_status_path)

def set_forward_status(on):
    if on:
        open(_status_path, "w").close()
    else:
        if os.path.exists(_status_path):
            os.remove(_status_path)
