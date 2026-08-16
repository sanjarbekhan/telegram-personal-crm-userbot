from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    load_dotenv()
    api_id = int(required("API_ID"))
    api_hash = required("API_HASH")
    phone_number = required("PHONE_NUMBER")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(phone=phone_number)
    print(
        "\nTELETHON_SESSION quyida. Uni hosting Environment Variables "
        "bo‘limiga qo‘ying:\n"
    )
    print(client.session.save())
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
