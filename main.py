import asyncio
import logging
import os
import sqlite3
import time

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

load_dotenv()

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
OWNER_ID = os.getenv("OWNER_ID")
SESSION_STRING = os.getenv("SESSION_STRING", "")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

if not API_ID:
    raise RuntimeError("Не задан API_ID")

if not API_HASH:
    raise RuntimeError("Не задан API_HASH")

if not OWNER_ID:
    raise RuntimeError("Не задан OWNER_ID")

API_ID = int(API_ID)
OWNER_ID = int(OWNER_ID)

DB_FILE = "database.sqlite3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =========================
# TELEGRAM
# =========================

if SESSION_STRING:
    user_client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH
    )
else:
    # Локальная session.
    # На BotHost лучше использовать SESSION_STRING.
    user_client = TelegramClient(
        "userbot",
        API_ID,
        API_HASH
    )

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================
# DATABASE
# =========================

db = sqlite3.connect(
    DB_FILE,
    check_same_thread=False
)

db.row_factory = sqlite3.Row

db.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER UNIQUE NOT NULL,
    title TEXT,
    username TEXT,
    enabled INTEGER DEFAULT 1,
    created_at INTEGER NOT NULL
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

db.commit()


def get_setting(key, default=None):
    row = db.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    ).fetchone()

    if row is None:
        return default

    return row["value"]


def set_setting(key, value):
    db.execute("""
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (key, str(value)))

    db.commit()


def owner_only(message: Message):
    return (
        message.from_user is not None
        and message.from_user.id == OWNER_ID
    )


# Значения по умолчанию
if get_setting("enabled") is None:
    set_setting("enabled", "0")

if get_setting("interval") is None:
    set_setting("interval", "900")

if get_setting("selected_text") is None:
    set_setting("selected_text", "0")


# =========================
# BOT COMMANDS
# =========================

@dp.message(Command("start"))
async def command_start(message: Message):
    if not owner_only(message):
        return

    await message.answer(
        "🤖 Autogroup\n\n"
        "Управление:\n\n"
        "/addchat ID — добавить группу\n"
        "/removechat ID — удалить группу\n"
        "/chats — список групп\n\n"
        "/texts — список текстов\n"
        "/addtext Название — добавить текст\n"
        "/selecttext ID — выбрать текст\n"
        "/deletetext ID — удалить текст\n\n"
        "/interval 15 — общий интервал\n"
        "/startsend — запустить\n"
        "/stopsend — остановить\n"
        "/status — состояние\n"
        "/myid — показать твой ID"
    )


@dp.message(Command("myid"))
async def command_myid(message: Message):
    if not owner_only(message):
        return

    await message.answer(
        f"🆔 Твой Telegram ID:\n{message.from_user.id}"
    )


# =========================
# CHATS
# =========================

@dp.message(Command("addchat"))
async def command_addchat(message: Message):
    if not owner_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "Использование:\n"
            "/addchat CHAT_ID"
        )
        return

    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    try:
        entity = await user_client.get_entity(chat_id)

        title = getattr(entity, "title", None)
        username = getattr(entity, "username", None)

        db.execute("""
            INSERT INTO chats
            (chat_id, title, username, enabled, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(chat_id)
            DO UPDATE SET
                enabled = 1,
                title = excluded.title,
                username = excluded.username
        """, (
            chat_id,
            title or str(chat_id),
            username,
            int(time.time())
        ))

        db.commit()

        await message.answer(
            "✅ Группа добавлена.\n\n"
            f"Название: {title or 'Без названия'}\n"
            f"ID: {chat_id}"
        )

    except Exception as e:
        logging.exception("Ошибка добавления группы")

        await message.answer(
            f"❌ Не удалось получить группу:\n{e}"
        )


@dp.message(Command("removechat"))
async def command_removechat(message: Message):
    if not owner_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "/removechat CHAT_ID"
        )
        return

    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    db.execute(
        "UPDATE chats SET enabled = 0 WHERE chat_id = ?",
        (chat_id,)
    )

    db.commit()

    await message.answer(
        f"🗑 Группа {chat_id} отключена."
    )


@dp.message(Command("chats"))
async def command_chats(message: Message):
    if not owner_only(message):
        return

    rows = db.execute("""
        SELECT chat_id, title, username
        FROM chats
        WHERE enabled = 1
        ORDER BY id
    """).fetchall()

    if not rows:
        await message.answer(
            "📋 Активных групп нет."
        )
        return

    result = ["📋 Группы:\n"]

    for number, row in enumerate(rows, 1):
        result.append(
            f"{number}. {row['title']}\n"
            f"   ID: {row['chat_id']}"
        )

    await message.answer("\n".join(result))


# =========================
# TEXTS
# =========================

@dp.message(Command("texts"))
async def command_texts(message: Message):
    if not owner_only(message):
        return

    rows = db.execute("""
        SELECT id, name
        FROM texts
        ORDER BY id
    """).fetchall()

    if not rows:
        await message.answer(
            "📝 Текстов пока нет."
        )
        return

    selected = int(
        get_setting("selected_text", "0")
    )

    result = ["📝 Тексты:\n"]

    for row in rows:
        mark = " ✅" if row["id"] == selected else ""

        result.append(
            f"{row['id']}. {row['name']}{mark}"
        )

    await message.answer(
        "\n".join(result)
    )


@dp.message(Command("addtext"))
async def command_addtext(message: Message):
    if not owner_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "Напиши:\n"
            "/addtext Название\n\n"
            "После этого следующим сообщением отправь текст."
        )
        return

    name = parts[1].strip()

    set_setting(
        "waiting_text_name",
        name
    )

    await message.answer(
        f"📝 Название: {name}\n\n"
        "Теперь отправь текст отдельным сообщением."
    )


@dp.message(Command("selecttext"))
async def command_selecttext(message: Message):
    if not owner_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "/selecttext ID"
        )
        return

    try:
        text_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ ID должен быть числом."
        )
        return

    row = db.execute(
        "SELECT name FROM texts WHERE id = ?",
        (text_id,)
    ).fetchone()

    if not row:
        await message.answer(
            "❌ Текст не найден."
        )
        return

    set_setting(
        "selected_text",
        text_id
    )

    await message.answer(
        f"✅ Выбран текст №{text_id}\n"
        f"{row['name']}"
    )


@dp.message(Command("deletetext"))
async def command_deletetext(message: Message):
    if not owner_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "/deletetext ID"
        )
        return

    try:
        text_id = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ ID должен быть числом."
        )
        return

    db.execute(
        "DELETE FROM texts WHERE id = ?",
        (text_id,)
    )

    db.commit()

    if int(get_setting("selected_text", "0")) == text_id:
        set_setting("selected_text", "0")

    await message.answer(
        f"🗑 Текст №{text_id} удалён."
    )


@dp.message()
async def receive_new_text(message: Message):
    if not owner_only(message):
        return

    waiting_name = get_setting(
        "waiting_text_name",
        ""
    )

    if not waiting_name:
        return

    if not message.text:
        return

    db.execute("""
        INSERT INTO texts
        (name, content, created_at)
        VALUES (?, ?, ?)
    """, (
        waiting_name,
        message.text,
        int(time.time())
    ))

    db.commit()

    text_id = db.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    set_setting(
        "waiting_text_name",
        ""
    )

    await message.answer(
        f"✅ Текст сохранён.\n\n"
        f"ID: {text_id}\n"
        f"Название: {waiting_name}"
    )


# =========================
# INTERVAL
# =========================

@dp.message(Command("interval"))
async def command_interval(message: Message):
    if not owner_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "/interval 15"
        )
        return

    try:
        minutes = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ Укажи количество минут."
        )
        return

    if minutes < 1:
        await message.answer(
            "❌ Минимальный интервал — 1 минута."
        )
        return

    set_setting(
        "interval",
        minutes * 60
    )

    await message.answer(
        f"⏱ Общий интервал: {minutes} минут."
    )


# =========================
# START / STOP
# =========================

@dp.message(Command("startsend"))
async def command_startsend(message: Message):
    if not owner_only(message):
        return

    selected = int(
        get_setting("selected_text", "0")
    )

    if selected == 0:
        await message.answer(
            "❌ Сначала выбери текст:\n"
            "/selecttext ID"
        )
        return

    count = db.execute("""
        SELECT COUNT(*)
        FROM chats
        WHERE enabled = 1
    """).fetchone()[0]

    if count == 0:
        await message.answer(
            "❌ Нет активных групп."
        )
        return

    set_setting(
        "enabled",
        "1"
    )

    await message.answer(
        "▶️ Рассылка запущена."
    )


@dp.message(Command("stopsend"))
async def command_stopsend(message: Message):
    if not owner_only(message):
        return

    set_setting(
        "enabled",
        "0"
    )

    await message.answer(
        "⏹ Рассылка остановлена."
    )


# =========================
# STATUS
# =========================

@dp.message(Command("status"))
async def command_status(message: Message):
    if not owner_only(message):
        return

    enabled = (
        get_setting("enabled", "0") == "1"
    )

    interval = int(
        get_setting("interval", "900")
    )

    selected = int(
        get_setting("selected_text", "0")
    )

    count = db.execute("""
        SELECT COUNT(*)
        FROM chats
        WHERE enabled = 1
    """).fetchone()[0]

    await message.answer(
        "📊 Статус\n\n"
        f"Рассылка: "
        f"{'🟢 включена' if enabled else '🔴 выключена'}\n"
        f"Групп: {count}\n"
        f"Интервал: {interval // 60} мин.\n"
        f"Текст: №{selected}"
    )


# =========================
# SENDER
# =========================

async def sender_loop():

    while True:

        try:

            if get_setting("enabled", "0") != "1":
                await asyncio.sleep(3)
                continue

            selected = int(
                get_setting("selected_text", "0")
            )

            row = db.execute(
                "SELECT content FROM texts WHERE id = ?",
                (selected,)
            ).fetchone()

            if not row:
                await asyncio.sleep(5)
                continue

            content = row["content"]

            chats = db.execute("""
                SELECT chat_id, title
                FROM chats
                WHERE enabled = 1
                ORDER BY id
            """).fetchall()

            if not chats:
                await asyncio.sleep(5)
                continue

            interval = int(
                get_setting("interval", "900")
            )

            for chat in chats:

                if get_setting("enabled", "0") != "1":
                    break

                try:

                    logging.info(
                        "Отправка: %s (%s)",
                        chat["title"],
                        chat["chat_id"]
                    )

                    await user_client.send_message(
                        chat["chat_id"],
                        content
                    )

                    logging.info(
                        "Успешно отправлено: %s",
                        chat["title"]
                    )

                except FloodWaitError as error:

                    logging.warning(
                        "Telegram FloodWait: %s секунд",
                        error.seconds
                    )

                    await asyncio.sleep(
                        error.seconds
                    )

                except Exception:

                    logging.exception(
                        "Ошибка отправки в %s",
                        chat["chat_id"]
                    )

                await asyncio.sleep(
                    interval
                )

        except Exception:

            logging.exception(
                "Ошибка sender_loop"
            )

            await asyncio.sleep(10)


# =========================
# MAIN
# =========================

async def main():

    logging.info(
        "Запуск Autogroup..."
    )

    if not SESSION_STRING:

        logging.warning(
            "SESSION_STRING не задан."
        )

        logging.warning(
            "Для BotHost необходимо сначала "
            "создать Telethon session."
        )

        raise RuntimeError(
            "Добавь переменную SESSION_STRING "
            "в BotHost."
        )

    await user_client.connect()

    if not await user_client.is_user_authorized():

        raise RuntimeError(
            "SESSION_STRING недействителен "
            "или аккаунт не авторизован."
        )

    me = await user_client.get_me()

    logging.info(
        "Личный аккаунт подключён: ID=%s",
        me.id
    )

    sender_task = asyncio.create_task(
        sender_loop()
    )

    try:

        await dp.start_polling(bot)

    finally:

        sender_task.cancel()

        await user_client.disconnect()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
