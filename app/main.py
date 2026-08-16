from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from telethon.tl.types import User

from app.admin_bot import create_dispatcher
from app.contact_import import scan_private_contacts
from app.config import Config
from app.dashboard import daily_dashboard_loop
from app.db import Database
from app.sender_worker import sender_loop
from app.userbot import (
    build_user_client,
    register_userbot_handlers,
    scan_recent_private_chats,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = Config.load()
    db = Database(cfg)

    admin_bot = Bot(token=cfg.admin_bot_token)
    user_client = build_user_client(cfg)
    register_userbot_handlers(user_client, db, admin_bot, cfg)

    await user_client.connect()
    if not await user_client.is_user_authorized():
        await user_client.disconnect()
        raise RuntimeError(
            "TELETHON_SESSION yaroqsiz yoki boshqa akkauntga tegishli. "
            "Uni lokal kompyuterda qayta yarating."
        )
    logger.info("Userbot connected")

    async def scan_func(days: int) -> int:
        return await scan_recent_private_chats(user_client, db, days=days)

    async def scan_contacts_func() -> list[int]:
        return await scan_private_contacts(user_client, db)

    async def resolve_username(username: str) -> dict:
        entity = await user_client.get_entity(f"@{username.lstrip('@')}")
        if not isinstance(entity, User):
            raise ValueError("Username shaxsiy Telegram foydalanuvchisiga tegishli emas")
        if entity.bot or entity.deleted or entity.is_self:
            raise ValueError("Bot, o‘chirilgan yoki o‘z akkauntingiz lead bo‘la olmaydi")
        full_name = " ".join(
            part for part in (entity.first_name, entity.last_name) if part
        ) or "Nomsiz"
        return {
            "telegram_user_id": entity.id,
            "full_name": full_name,
            "username": entity.username,
        }

    async def send_user_message(telegram_user_id: int, text: str) -> None:
        entity = await user_client.get_entity(telegram_user_id)
        if not isinstance(entity, User) or entity.bot or entity.deleted or entity.is_self:
            raise ValueError("Qabul qiluvchi shaxsiy Telegram foydalanuvchisi emas")
        await user_client.send_message(entity, text, parse_mode=None)

    if cfg.run_initial_scan:
        logger.info("Initial scan started")
        asyncio.create_task(scan_func(cfg.scan_days))

    dp = create_dispatcher(
        cfg,
        db,
        scan_func,
        scan_contacts_func,
        send_user_message=send_user_message,
        resolve_username=resolve_username,
    )

    await asyncio.gather(
        dp.start_polling(admin_bot),
        sender_loop(user_client, admin_bot, db, cfg),
        daily_dashboard_loop(admin_bot, db, cfg),
        user_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
