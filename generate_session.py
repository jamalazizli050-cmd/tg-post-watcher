import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\nТВОЯ USER_SESSION:\n")
    print(client.session.save())