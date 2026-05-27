import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_SESSION = os.getenv("USER_SESSION")

WEEKLY_TARGET_IDS = [
    int(user_id.strip())
    for user_id in os.getenv("WEEKLY_TARGET_IDS", "").split(",")
    if user_id.strip().isdigit()
]

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
WEEKLY_POSTS_FILE = "weekly_posts.json"

BAKU_TIMEZONE = ZoneInfo("Asia/Baku")

user_client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
bot_client = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

scheduler = AsyncIOScheduler(timezone=BAKU_TIMEZONE)


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
        return True

    return False


def load_weekly_posts():
    if not os.path.exists(WEEKLY_POSTS_FILE):
        return []

    try:
        with open(WEEKLY_POSTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return []


def save_weekly_post(post):
    posts = load_weekly_posts()

    # защита от дублей по ссылке
    if any(existing_post.get("link") == post["link"] for existing_post in posts):
        return

    posts.append(post)

    with open(WEEKLY_POSTS_FILE, "w", encoding="utf-8") as file:
        json.dump(posts, file, ensure_ascii=False, indent=2)


def clear_weekly_posts():
    with open(WEEKLY_POSTS_FILE, "w", encoding="utf-8") as file:
        json.dump([], file, ensure_ascii=False, indent=2)


def shorten_text(text, max_length):
    if len(text) > max_length:
        return text[:max_length] + "\n\n...текст обрезан"
    return text


def build_weekly_summary(posts):
    if not posts:
        return (
            "🎨 Еженедельная сводка артов\n\n"
            "За неделю было пусто."
        )

    lines = [
        "🎨 Еженедельная сводка артов",
        "",
        f"Всего постов: {len(posts)}",
        "",
    ]

    for index, post in enumerate(posts, start=1):
        text = post.get("text", "Без текста")
        text = shorten_text(text, 180)

        lines.append(f"{index}. {post.get('channel_name', 'Unknown channel')}")
        lines.append(text)
        lines.append(post.get("link", "Ссылки нет"))
        lines.append("")

    return "\n".join(lines)


async def send_weekly_summary():
    posts = load_weekly_posts()
    summary = build_weekly_summary(posts)

    if not WEEKLY_TARGET_IDS:
        print("WEEKLY_TARGET_IDS пустой. Некуда отправлять недельную сводку.")
        return

    for target_id in WEEKLY_TARGET_IDS:
        try:
            await bot_client.send_message(target_id, summary)
        except Exception as error:
            print(f"Не смог отправить weekly summary пользователю {target_id}: {error}")

    clear_weekly_posts()
    print("Еженедельная сводка отправлена и weekly_posts.json очищен.")


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

    full_text = message.text or message.caption or ""

    if TARGET_TAG.lower() not in full_text.lower():
        return

    channel_name = getattr(chat, "title", "Unknown channel")
    username = getattr(chat, "username", None)

    if username:
        link = f"https://t.me/{username}/{message.id}"
    else:
        link = "Приватный канал — публичной ссылки нет"

    text_for_message = full_text.strip() or "Новый пост без текста"
    text_for_message = shorten_text(text_for_message, MAX_TEXT_LENGTH)

    post_text = f"🎨 Найден арт из: {channel_name}\n\n{text_for_message}\n\n🔗 {link}"

    # Сохраняем в недельную сводку
    save_weekly_post({
        "channel_name": channel_name,
        "username": username,
        "text": full_text.strip() or "Новый пост без текста",
        "link": link,
        "date": datetime.now(BAKU_TIMEZONE).isoformat(),
    })

    # Сразу отправляем всем подписчикам
    subscribers = load_subscribers()

    if not subscribers:
        print("Пост найден и сохранён в weekly_posts.json, но подписчиков пока нет.")
        return

    for user_id in subscribers:
        try:
            await bot_client.send_message(user_id, post_text)
        except Exception as error:
            print(f"Не смог отправить пользователю {user_id}: {error}")


async def main():
    await user_client.start()

    # Каждую субботу в 12:00 по Баку отправляет сводку и чистит weekly_posts.json
    scheduler.add_job(send_weekly_summary, "cron", day_of_week="sat", hour=12, minute=0)
    scheduler.start()

    print("Бот запущен. Собираем только посты с #cliqueart.")
    print("Подписка работает через /start.")
    print("Еженедельная сводка: каждую субботу в 12:00 по Баку.")
    print(f"Weekly target IDs: {WEEKLY_TARGET_IDS}")

    await user_client.run_until_disconnected()


user_client.loop.run_until_complete(main())