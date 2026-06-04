import os
import json
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telethon import Button, TelegramClient, events
from telethon.sessions import StringSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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


def parse_target_ids(raw_value):
    target_ids = []

    for raw_id in raw_value.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue

        try:
            target_ids.append(int(raw_id))
        except ValueError:
            print(f"Пропускаю некорректный WEEKLY_TARGET_IDS id: {raw_id}")

    return target_ids


WEEKLY_TARGET_IDS = parse_target_ids(os.getenv("WEEKLY_TARGET_IDS", ""))


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


def remove_subscriber(user_id):
    subscribers = load_subscribers()

    if user_id not in subscribers:
        return False

    subscribers.remove(user_id)

    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as file:
        for subscriber_id in sorted(subscribers):
            file.write(f"{subscriber_id}\n")

    return True


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


def build_post_data(chat, message, full_text):
    channel_name = getattr(chat, "title", "Unknown channel")
    username = getattr(chat, "username", None)

    if username:
        link = f"https://t.me/{username}/{message.id}"
    else:
        link = "Приватный канал — публичной ссылки нет"

    text_for_message = full_text.strip() or "Новый пост без текста"
    text_for_message = shorten_text(text_for_message, MAX_TEXT_LENGTH)
    post_text = (
        f"🎨 {channel_name}\n"
        f"━━━━━━━━━━━━\n\n"
        f"{text_for_message}\n\n"
        f"🔗 {link}"
    )

    return channel_name, username, link, post_text


def bot_menu_buttons():
    return [
        [Button.text("ℹ️ Help"), Button.text("🚫 Отписаться")],
    ]


def help_text():
    return (
        "🎨 #cliqueart watcher\n\n"
        "Я присылаю новые посты с #cliqueart из отслеживаемых каналов.\n\n"
        "/start — подписаться на обычные уведомления\n"
        "/unsubscribe — отписаться от обычных уведомлений\n"
        "/help — показать эту подсказку\n\n"
        "Еженедельная сводка отправляется только в чаты из WEEKLY_TARGET_IDS в .env."
    )


async def send_post_notification(user_id, post_text, media_paths):
    if not media_paths:
        await bot_client.send_message(user_id, post_text)
        return

    for start in range(0, len(media_paths), 10):
        media_chunk = media_paths[start:start + 10]
        caption = post_text if start == 0 else None
        file_to_send = media_chunk[0] if len(media_chunk) == 1 else media_chunk
        await bot_client.send_file(
            user_id,
            file_to_send,
            caption=caption,
            supports_streaming=True,
        )


async def notify_subscribers(subscribers, post_text, media_messages):
    media_paths = []

    if media_messages:
        with tempfile.TemporaryDirectory() as temp_dir:
            for media_message in media_messages:
                try:
                    media_path = await user_client.download_media(media_message, file=temp_dir)
                except Exception as error:
                    print(f"Не смог скачать медиа из поста: {error}")
                    continue

                if media_path:
                    media_paths.append(media_path)

            for user_id in subscribers:
                try:
                    await send_post_notification(user_id, post_text, media_paths)
                except Exception as error:
                    print(f"Не смог отправить пользователю {user_id}: {error}")
        return

    for user_id in subscribers:
        try:
            await send_post_notification(user_id, post_text, media_paths)
        except Exception as error:
            print(f"Не смог отправить пользователю {user_id}: {error}")


def build_weekly_summary(posts):
    if not posts:
        return (
            "🎨 Weekly #cliqueart\n"
            "━━━━━━━━━━━━\n\n"
            "За неделю было пусто."
        )

    lines = [
        "🎨 Weekly #cliqueart",
        "━━━━━━━━━━━━",
        "",
        f"Постов за неделю: {len(posts)}",
        "",
    ]

    for index, post in enumerate(posts, start=1):
        text = post.get("text", "Без текста")
        text = shorten_text(text, 180)

        lines.append(f"{index}. 🎨 {post.get('channel_name', 'Unknown channel')}")
        lines.append(text)
        lines.append(f"🔗 {post.get('link', 'Ссылки нет')}")
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
            "Теперь я буду кидать сюда новые арты из отслеживаемых каналов.",
            buttons=bot_menu_buttons(),
        )
    else:
        await event.reply(
            "Ты уже подписан ✅\n\n"
            "Ждём новые посты с #cliqueart.",
            buttons=bot_menu_buttons(),
        )


@bot_client.on(events.NewMessage(pattern="/help"))
async def help_handler(event):
    await event.reply(help_text(), buttons=bot_menu_buttons())


@bot_client.on(events.NewMessage(pattern="/unsubscribe"))
async def unsubscribe_handler(event):
    if remove_subscriber(event.sender_id):
        await event.reply(
            "Готово, отписал от обычных уведомлений.\n\n"
            "Weekly всё равно живёт отдельно и отправляется только в WEEKLY_TARGET_IDS.",
            buttons=bot_menu_buttons(),
        )
    else:
        await event.reply(
            "Ты и так не был подписан на обычные уведомления.",
            buttons=bot_menu_buttons(),
        )


@bot_client.on(events.NewMessage(pattern="(?i)^(ℹ️ Help|Help|Помощь)$"))
async def help_button_handler(event):
    await help_handler(event)


@bot_client.on(events.NewMessage(pattern="(?i)^(🚫 Отписаться|Отписаться)$"))
async def unsubscribe_button_handler(event):
    await unsubscribe_handler(event)


@bot_client.on(events.NewMessage(pattern="/subscribers"))
async def subscribers_handler(event):
    subscribers = load_subscribers()
    await event.reply(f"👥 Подписчиков: {len(subscribers)}")


@user_client.on(events.Album(chats=CHANNELS))
async def new_album_handler(event):
    chat = await event.get_chat()
    messages = event.messages
    first_message = messages[0]

    full_text = "\n".join(
        (message.text or message.caption or "").strip()
        for message in messages
        if message.text or message.caption
    )

    if TARGET_TAG.lower() not in full_text.lower():
        return

    channel_name, username, link, post_text = build_post_data(chat, first_message, full_text)

    save_weekly_post({
        "channel_name": channel_name,
        "username": username,
        "text": full_text.strip() or "Новый пост без текста",
        "link": link,
        "date": datetime.now(BAKU_TIMEZONE).isoformat(),
    })

    subscribers = load_subscribers()

    if not subscribers:
        print("Пост найден и сохранён в weekly_posts.json, но подписчиков пока нет.")
        return

    media_messages = [message for message in messages if message.media]
    await notify_subscribers(subscribers, post_text, media_messages)


@user_client.on(events.NewMessage(chats=CHANNELS))
async def new_post_handler(event):
    chat = await event.get_chat()
    message = event.message

    if message.grouped_id:
        return

    full_text = message.text or message.caption or ""

    if TARGET_TAG.lower() not in full_text.lower():
        return

    channel_name, username, link, post_text = build_post_data(chat, message, full_text)

    # Сохраняем в недельную сводку
    save_weekly_post({
        "channel_name": channel_name,
        "username": username,
        "text": full_text.strip() or "Новый пост без текста",
        "link": link,
        "date": datetime.now(BAKU_TIMEZONE).isoformat(),
    })

    subscribers = load_subscribers()

    if not subscribers:
        print("Пост найден и сохранён в weekly_posts.json, но подписчиков пока нет.")
        return

    for user_id in subscribers:
        try:
            if message.media:
                with tempfile.TemporaryDirectory() as temp_dir:
                    media_path = await user_client.download_media(message, file=temp_dir)
                    await send_post_notification(
                        user_id,
                        post_text,
                        [media_path] if media_path else [],
                    )
            else:
                await send_post_notification(user_id, post_text, [])
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
