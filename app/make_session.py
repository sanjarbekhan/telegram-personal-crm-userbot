from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import Config


async def main() -> None:
    cfg = Config.load()
    client = TelegramClient(StringSession(), cfg.api_id, cfg.api_hash)
    await client.start(phone=cfg.phone_number)
    print("\nTELETHON_SESSION quyida. Uni Render Environment Variables ichiga qo‘ying:\n")
    print(client.session.save())
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
