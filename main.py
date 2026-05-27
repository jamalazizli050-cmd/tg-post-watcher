import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUR_ID = int(os.getenv("YOUR_ID"))
USER_SESSION = os.getenv("USER_SESSION")

CHANNELS = [
    "miLLLkaArts",
    "reggiekid",
    "potaeto505",
    "lighty_19871983",
    "supertsigan",
    "markofmeow",
    "oretvsebiya",
    "skisskefir",
    "cinnabarts",
    "tosamoeshtobbulo",
    "clancy0001",
    "vval_jpg",
    "artstlv",
    "trench_camp",
    "cyg_speaks",
    "mafchhh",
    "camaldocs",
]

TARGET_TAG = "#cliqueart"
MAX_TEXT_LENGTH = 100

user_client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
bot_client = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)


@user_client.on(events.NewMessage(chats=CHANNELS))
async def new_post_handler(event):
    chat = await event.get_chat()
    message = event.message

    text = message.text or message.caption or ""

    # Пропускаем пост, если нет нужного тега
    if TARGET_TAG.lower() not in text.lower():
        return

    channel_name = getattr(chat, "title", "Unknown channel")
    username = getattr(chat, "username", None)

    if username:
        link = f"https://t.me/{username}/{message.id}"
    else:
        link = "Приватный канал — публичной ссылки нет"

    if not text.strip():
        text = "Новый пост без текста"

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n\n...текст обрезан"

    post_text = f"🎨 Найден арт из: {channel_name}\n\n{text}\n\n🔗 {link}"

    await bot_client.send_message(YOUR_ID, post_text)


async def main():
    await user_client.start()
    print("Бот запущен. Собираем только посты с #cliqueart...")
    await user_client.run_until_disconnected()


user_client.loop.run_until_complete(main())