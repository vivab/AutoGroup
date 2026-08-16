import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from telethon import TelegramClient
from telethon.errors import FloodWaitError

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
OWNER_ID = int(os.environ["OWNER_ID"])

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

client = TelegramClient(
    "userbot",
    API_ID,
    API_HASH
)

db = sqlite3.connect("data.db")

db.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

db.commit()


def get(key, default=""):
    r = db.execute(
        "SELECT value FROM config WHERE key=?",
        (key,)
    ).fetchone()

    return r[0] if r else default


def set_(key, value):
    db.execute(
        "INSERT OR REPLACE INTO config VALUES (?,?)",
        (key, str(value))
    )
    db.commit()


def owner(m):
    return m.from_user and m.from_user.id == OWNER_ID


@dp.message(Command("start"))
async def start(m: Message):
    if not owner(m):
        return

    await m.answer(
        "Команды:\n\n"
        "/д ID — добавить группу\n"
        "/у ID — удалить группу\n"
        "/список — группы\n"
        "/текст — изменить текст\n"
        "/интервал 15 — интервал в минутах\n"
        "/старт — запуск\n"
        "/стоп — остановка"
    )


@dp.message(Command("д"))
async def add(m: Message):
    if not owner(m):
        return

    try:
        chat_id = int(m.text.split(maxsplit=1)[1])
        await client.get_entity(chat_id)

        db.execute(
            "INSERT OR IGNORE INTO chats VALUES (?)",
            (chat_id,)
        )
        db.commit()

        await m.answer(f"✅ Добавлено: {chat_id}")

    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("у"))
async def remove(m: Message):
    if not owner(m):
        return

    try:
        chat_id = int(m.text.split(maxsplit=1)[1])

        db.execute(
            "DELETE FROM chats WHERE id=?",
            (chat_id,)
        )
        db.commit()

        await m.answer(f"🗑 Удалено: {chat_id}")

    except:
        await m.answer("Использование: /у ID")


@dp.message(Command("список"))
async def chats(m: Message):
    if not owner(m):
        return

    rows = db.execute(
        "SELECT id FROM chats"
    ).fetchall()

    if not rows:
        await m.answer("Список пуст.")
        return

    await m.answer(
        "Группы:\n" +
        "\n".join(str(x[0]) for x in rows)
    )


@dp.message(Command("текст"))
async def text(m: Message):
    if not owner(m):
        return

    value = m.text.partition(" ")[2].strip()

    if not value:
        await m.answer(
            "Использование:\n"
            "/текст Ваш текст"
        )
        return

    set_("text", value)

    await m.answer("✅ Текст изменён.")


@dp.message(Command("интервал"))
async def interval(m: Message):
    if not owner(m):
        return

    try:
        minutes = int(
            m.text.split(maxsplit=1)[1]
        )

        if minutes < 1:
            raise ValueError

        set_("interval", minutes * 60)

        await m.answer(
            f"⏱ Интервал: {minutes} минут."
        )

    except:
        await m.answer(
            "Использование: /интервал 15"
        )


@dp.message(Command("старт"))
async def run(m: Message):
    if not owner(m):
        return

    if not get("text"):
        await m.answer(
            "❌ Сначала задай текст."
        )
        return

    set_("running", "1")

    await m.answer("▶️ Запущено.")


@dp.message(Command("стоп"))
async def stop(m: Message):
    if not owner(m):
        return

    set_("running", "0")

    await m.answer("⏹ Остановлено.")


async def sender():
    while True:

        if get("running") != "1":
            await asyncio.sleep(2)
            continue

        text = get("text")

        if not text:
            await asyncio.sleep(2)
            continue

        rows = db.execute(
            "SELECT id FROM chats"
        ).fetchall()

        interval = int(
            get("interval", "900")
        )

        for (chat_id,) in rows:

            if get("running") != "1":
                break

            try:
                await client.send_message(
                    chat_id,
                    text
                )

            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)

            except Exception as e:
                print(
                    f"Ошибка {chat_id}: {e}"
                )

            await asyncio.sleep(interval)


async def main():

    await client.start()

    me = await client.get_me()

    print(
        f"Личный аккаунт подключён: {me.id}"
    )

    asyncio.create_task(sender())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
