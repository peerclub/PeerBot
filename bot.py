import re
import asyncio
import aiosqlite
from typing import Any
from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import Router, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, ChatPermissions, ChatMemberUpdated
from aiogram.filters import Command, CommandObject, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from pymorphy2 import MorphAnalyzer

DB_PATH = "bot_data.db"
router = Router()
router.message.filter(F.chat.type == "supergroup")

morph = MorphAnalyzer(lang="ru")
triggers = ["клоун", "дурак", "блинк"]


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                reputation INTEGER DEFAULT 0,
                warns INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS mutes (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()


async def add_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def update_reputation(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET reputation = reputation + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()


async def add_warn(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET warns = warns + 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def reset_warns(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET warns = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def add_message(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET messages = messages + 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_top_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, messages FROM users ORDER BY messages DESC LIMIT 10") as cursor:
            return await cursor.fetchall()


async def set_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()


async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None


async def add_ban(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO bans (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def remove_ban(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_ban_list():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM bans") as cursor:
            return await cursor.fetchall()


async def add_mute(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO mutes (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def remove_mute(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_mute_list():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM mutes") as cursor:
            return await cursor.fetchall()


@router.message(Command("profile"))
async def profile(message: Message):
    await add_user(message.from_user.id)
    user = await get_user(message.from_user.id)

    text = f"👤 Профиль {message.from_user.first_name}\n⭐ Репутация: {user[1]}\n⚠️ Предупреждения: {user[2]}\n📩 Сообщений: {user[3]}"
    await message.answer(text)


@router.message(Command("setadmin"))
async def set_admin_command(message: Message):
    reply = message.reply_to_message
    if not reply:
        return await message.answer("👀 Пользователь не найден!")

    await set_admin(reply.from_user.id)
    await message.answer(f"✅ {reply.from_user.first_name} теперь администратор!")


@router.message(Command("removeadmin"))
async def remove_admin_command(message: Message):
    reply = message.reply_to_message
    if not reply:
        return await message.answer("👀 Пользователь не найден!")

    await remove_admin(reply.from_user.id)
    await message.answer(f"❌ {reply.from_user.first_name} больше не администратор.")


@router.message(Command("unmute"))
async def unmute_command(message: Message, bot: Bot):
    reply = message.reply_to_message
    if not reply:
        return await message.answer("👀 Пользователь не найден!")

    await bot.restrict_chat_member(chat_id=message.chat.id, user_id=reply.from_user.id, permissions=ChatPermissions(can_send_messages=True))
    await remove_mute(reply.from_user.id)
    await message.answer(f"🔊 {reply.from_user.first_name} теперь может писать!")


@router.message(Command("unban"))
async def unban_command(message: Message, bot: Bot):
    reply = message.reply_to_message
    if not reply:
        return await message.answer("👀 Пользователь не найден!")

    await bot.unban_chat_member(chat_id=message.chat.id, user_id=reply.from_user.id)
    await remove_ban(reply.from_user.id)
    await message.answer(f"✅ {reply.from_user.first_name} разбанен!")


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def greet_new_member(event: ChatMemberUpdated):
    await event.chat.send_message(f"👋 Добро пожаловать, {event.new_chat_member.user.full_name}!")


async def main():
    await init_db()
    bot = Bot("ТВОЙ_ТОКЕН", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
