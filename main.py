import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
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
SUBSCRIBERS_FILE = "subscribers.txt"

user_client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
bot_client = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)


def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return set()

    with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as file:
        return set(
            int(line.strip())
            for line in file
            if line.strip().isdigit()
        )


def save_subscriber(user_id):
    subscribers = load_subscribers()

    if user_id not in subscribers:
        with open(SUBSCRIBERS_FILE, "a", encoding="utf-8") as file:
            file.write(f"{user_id}\n")

    return user_id not in subscribers


@bot_client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    user_id = event.sender_id
    is_new = save_subscriber(user_id)

    if is_new:
        await event.reply(
            "✅ Ты подписался на #cliqueart уведомления.\n\n"
            "Теперь я буду кидать сюда новые арты из отслеживаемых каналов."
        )
    else:
        await event.reply(
            "Ты уже подписан ✅\n\n"
            "Ждём новые посты с #cliqueart."
        )


@bot_client.on(events.NewMessage(pattern="/subscribers"))
async def subscribers_handler(event):
    subscribers = load_subscribers()

    await event.reply(f"👥 Подписчиков: {len(subscribers)}")


@user_client.on(events.NewMessage(chats=CHANNELS))
async def new_post_handler(event):
    chat = await event.get_chat()
    message = event.message

    text = message.text or message.caption or ""

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

    subscribers = load_subscribers()

    if not subscribers:
        print("Пост найден, но подписчиков пока нет.")
        return

    for user_id in subscribers:
        try:
            await bot_client.send_message(user_id, post_text)
        except Exception as error:
            print(f"Не смог отправить пользователю {user_id}: {error}")


async def main():
    await user_client.start()
    print("Бот запущен. Собираем только посты с #cliqueart...")
    print("Подписка работает через /start.")
    await user_client.run_until_disconnected()


user_client.loop.run_until_complete(main())