from telethon.sync import TelegramClient
import os
from dotenv import load_dotenv
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
with TelegramClient('userbot_session', API_ID, API_HASH) as client:
    client.send_message('me', 'Сессия создана!')
