
import os
from dotenv import load_dotenv
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "session")
SOURCE_CHAT_IDS = list(map(int, os.getenv("SOURCE_CHAT_IDS", "").split(",")))
TARGET_CHAT_IDS = list(map(int, os.getenv("TARGET_CHAT_IDS", "").split(",")))
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
FLASK_PASSWORD = os.getenv("FLASK_PASSWORD", "admin")

FORWARD_FLAG_FILE = "forwarder/.forward_on"

def ENABLE_FORWARD():
    return os.path.exists(FORWARD_FLAG_FILE)

def set_forward_status(on: bool):
    if on:
        open(FORWARD_FLAG_FILE, "w").close()
    else:
        try: os.remove(FORWARD_FLAG_FILE)
        except FileNotFoundError: pass
