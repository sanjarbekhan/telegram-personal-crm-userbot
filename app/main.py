from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.admin_bot import create_dispatcher
from app.config import Config
from app.db import Database
from app.sender_worker import sender_loop
from app.userbot import build_user_client, register_userbot_handlers, scan_recent_private_chats


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = Config.load()
    db = Database(cfg)

    admin_bot = Bot(token=cfg.admin_bot_token)
    user_client = build_user_client(cfg)

    register_userbot_handlers(user_client, db)

    await user_client.start(phone=cfg.phone_number)
    logger.info("Userbot connected")

    async def scan_func(days: int) -> int:
        return await scan_recent_private_chats(user_client, db, days=days)

    if cfg.run_initial_scan:
        logger.info("Initial scan started")
        asyncio.create_task(scan_func(cfg.scan_days))

    dp = create_dispatcher(cfg, db, scan_func)

    await asyncio.gather(
        dp.start_polling(admin_bot),
        sender_loop(user_client, admin_bot, db, cfg),
        user_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
