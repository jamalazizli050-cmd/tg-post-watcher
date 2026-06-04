import os
import json
import re
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
POST_LINK_PATTERN = re.compile(r"https://t\.me/(?P<username>[^/\s]+)/(?P<message_id>\d+)")

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


def build_weekly_post(chat, messages, full_text):
    first_message = messages[0]
    channel_name, username, link, post_text = build_post_data(chat, first_message, full_text)

    return {
        "channel_name": channel_name,
        "chat_id": getattr(chat, "id", None),
        "username": username,
        "text": full_text.strip() or "Новый пост без текста",
        "link": link,
        "date": datetime.now(BAKU_TIMEZONE).isoformat(),
        "message_ids": [message.id for message in messages],
        "media_ids": [message.id for message in messages if message.media],
    }, post_text


def bot_menu_buttons():
    return [
        [
            Button.inline("Help", b"help"),
            Button.inline("Weekly", b"weekly"),
        ],
        [Button.inline("Отписаться", b"unsubscribe")],
    ]


def help_text():
    return (
        "🎨 #cliqueart watcher\n\n"
        "Я присылаю новые посты с #cliqueart из отслеживаемых каналов.\n"
        "/start — подписаться на обычные уведомления\n"
        "/unsubscribe — отписаться от обычных уведомлений\n"
        "/weekly — прислать текущую weekly-подборку без очистки кеша"
    )


async def clear_old_keyboard(chat_id):
    await bot_client.send_message(
        chat_id,
        "Убрал старую клавиатуру.",
        buttons=Button.clear(),
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


def build_weekly_header(posts):
    if not posts:
        return (
            "🎨 Weekly #cliqueart\n"
            "━━━━━━━━━━━━\n\n"
            "За неделю было пусто."
        )

    return (
        "🎨 Weekly #cliqueart\n"
        "━━━━━━━━━━━━\n\n"
        f"Постов за неделю: {len(posts)}"
    )


def sort_weekly_posts(posts):
    def date_key(post):
        raw_date = post.get("date", "")

        try:
            return datetime.fromisoformat(raw_date)
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=BAKU_TIMEZONE)

    return sorted(posts, key=date_key)


def chunk_items(items, chunk_size):
    for start in range(0, len(items), chunk_size):
        yield items[start:start + chunk_size]


def parse_post_link(link):
    match = POST_LINK_PATTERN.search(link or "")
    if not match:
        return None, None

    return match.group("username"), int(match.group("message_id"))


def build_weekly_text(posts):
    lines = [build_weekly_header(posts)]

    for index, post in enumerate(posts, start=1):
        lines.extend([
            "",
            f"{index}. 🎨 {post.get('channel_name', 'Unknown channel')}",
            shorten_text(post.get("text", "Без текста"), 180),
            f"🔗 {post.get('link', 'Ссылки нет')}",
        ])

    return "\n".join(lines)


def build_no_media_weekly_text(posts):
    lines = [
        "📝 Weekly без медиа",
        "━━━━━━━━━━━━",
        "",
        f"Постов без медиа: {len(posts)}",
    ]

    for item in posts:
        post = item["post"]
        lines.extend([
            "",
            f"{item['index']}. 🎨 {post.get('channel_name', 'Unknown channel')}",
            shorten_text(post.get("text", "Без текста"), 180),
            f"🔗 {post.get('link', 'Ссылки нет')}",
        ])

    return "\n".join(lines)


def build_weekly_media_caption(posts, chunk, chunk_number, total_chunks):
    lines = [
        build_weekly_header(posts),
        "",
        f"Медиа {chunk_number}/{total_chunks}",
        "",
    ]

    for item in chunk:
        lines.append(
            f"{item['index']}. 🎨 {item['channel_name']}\n"
            f"🔗 {item['link']}"
        )

    caption = "\n\n".join(lines)
    if len(caption) > 1000:
        caption = caption[:980].rstrip() + "\n\n...ещё ссылки в следующих постах"

    return caption


async def get_weekly_media_items(post, post_index, temp_dir):
    link_username, link_message_id = parse_post_link(post.get("link"))
    chat_ref = post.get("username") or link_username or post.get("chat_id")
    media_ids = post.get("media_ids") or post.get("message_ids") or []
    media_items = []

    if not media_ids and link_message_id:
        media_ids = [link_message_id]

    if not chat_ref or not media_ids:
        print(
            "Нет данных для weekly-медиа: "
            f"{post.get('channel_name', 'Unknown channel')} / {post.get('link', 'no link')}"
        )
        return media_items

    try:
        messages = await user_client.get_messages(chat_ref, ids=media_ids)
    except Exception as error:
        print(f"Не смог получить weekly-медиа из {chat_ref}: {error}")
        return media_items

    if not isinstance(messages, list):
        messages = [messages]

    for message in messages:
        if not message or not message.media:
            continue

        try:
            media_path = await user_client.download_media(message, file=temp_dir)
        except Exception as error:
            print(f"Не смог скачать weekly-медиа из {chat_ref}: {error}")
            continue

        if media_path:
            media_items.append({
                "index": post_index,
                "channel_name": post.get("channel_name", "Unknown channel"),
                "link": post.get("link", "Ссылки нет"),
                "path": media_path,
            })

    if not media_items:
        print(
            "Weekly-медиа не найдено в сообщениях: "
            f"{post.get('channel_name', 'Unknown channel')} / ids={media_ids}"
        )

    return media_items


async def send_weekly_posts(target_id, posts):
    posts = sort_weekly_posts(posts)

    if not posts:
        await bot_client.send_message(target_id, build_weekly_header(posts))
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        media_items = []
        posts_without_media = []

        for index, post in enumerate(posts, start=1):
            post_media_items = await get_weekly_media_items(post, index, temp_dir)

            if post_media_items:
                media_items.extend(post_media_items)
            else:
                posts_without_media.append({
                    "index": index,
                    "post": post,
                })

        if not media_items:
            await bot_client.send_message(target_id, build_weekly_text(posts))
            return

        chunks = list(chunk_items(media_items, 10))
        total_chunks = len(chunks)

        for chunk_number, chunk in enumerate(chunks, start=1):
            caption = build_weekly_media_caption(posts, chunk, chunk_number, total_chunks)
            await bot_client.send_file(
                target_id,
                [item["path"] for item in chunk],
                caption=caption,
                supports_streaming=True,
            )

        if posts_without_media:
            await bot_client.send_message(
                target_id,
                build_no_media_weekly_text(posts_without_media),
            )


async def send_weekly_summary(clear_cache=True):
    posts = load_weekly_posts()

    if not WEEKLY_TARGET_IDS:
        print("WEEKLY_TARGET_IDS пустой. Некуда отправлять недельную сводку.")
        return

    for target_id in WEEKLY_TARGET_IDS:
        try:
            await send_weekly_posts(target_id, posts)
        except Exception as error:
            print(f"Не смог отправить weekly summary пользователю {target_id}: {error}")

    if clear_cache:
        clear_weekly_posts()
        print("Еженедельная сводка отправлена и weekly_posts.json очищен.")
    else:
        print("Еженедельная сводка отправлена без очистки weekly_posts.json.")


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


@bot_client.on(events.NewMessage(pattern="/weekly"))
async def weekly_handler(event):
    await event.reply("Ок, кидаю текущую weekly-подборку. Кеш не очищаю.")
    await send_weekly_posts(event.sender_id, load_weekly_posts())


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


@bot_client.on(events.CallbackQuery(data=b"help"))
async def help_button_handler(event):
    await event.answer()
    await event.respond(help_text(), buttons=bot_menu_buttons())


@bot_client.on(events.CallbackQuery(data=b"weekly"))
async def weekly_button_handler(event):
    await event.answer("Кидаю weekly")
    await event.respond("Ок, кидаю текущую weekly-подборку. Кеш не очищаю.")
    await send_weekly_posts(event.sender_id, load_weekly_posts())


@bot_client.on(events.CallbackQuery(data=b"unsubscribe"))
async def unsubscribe_button_handler(event):
    await event.answer()

    if remove_subscriber(event.sender_id):
        await event.respond(
            "Готово, отписал от обычных уведомлений.\n\n"
            "Weekly живёт отдельно и отправляется только в WEEKLY_TARGET_IDS.",
            buttons=bot_menu_buttons(),
        )
    else:
        await event.respond(
            "Ты и так не был подписан на обычные уведомления.",
            buttons=bot_menu_buttons(),
        )


@bot_client.on(events.NewMessage(pattern="(?i)^(ℹ️ Help|Help|Помощь)$"))
async def old_help_button_handler(event):
    await clear_old_keyboard(event.chat_id)
    await help_handler(event)


@bot_client.on(events.NewMessage(pattern="(?i)^(Weekly|Викли|Неделя)$"))
async def old_weekly_button_handler(event):
    await clear_old_keyboard(event.chat_id)
    await weekly_handler(event)


@bot_client.on(events.NewMessage(pattern="(?i)^(🚫 Отписаться|Отписаться)$"))
async def old_unsubscribe_button_handler(event):
    await clear_old_keyboard(event.chat_id)
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

    weekly_post, post_text = build_weekly_post(chat, messages, full_text)

    save_weekly_post(weekly_post)

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

    weekly_post, post_text = build_weekly_post(chat, [message], full_text)

    save_weekly_post(weekly_post)

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
