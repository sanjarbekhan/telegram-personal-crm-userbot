from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User

from app.config import Config
from app.db import Database


def build_user_client(cfg: Config) -> TelegramClient:
    if cfg.telethon_session:
        session = StringSession(cfg.telethon_session)
    else:
        # Local development only. Render filesystem is not persistent, use TELETHON_SESSION there.
        session = "userbot"
    return TelegramClient(session, cfg.api_id, cfg.api_hash)


def _full_name(user: User) -> str:
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join([p for p in parts if p]) or "Unknown"


def _is_valid_customer_user(user: Any) -> bool:
    if not isinstance(user, User):
        return False
    if getattr(user, "bot", False):
        return False
    if getattr(user, "is_self", False):
        return False
    if getattr(user, "deleted", False):
        return False
    return True


async def save_message_from_event(db: Database, event: events.NewMessage.Event) -> None:
    if not event.is_private:
        return

    chat = await event.get_chat()
    if not _is_valid_customer_user(chat):
        return

    msg = event.message
    customer = db.upsert_customer(
        telegram_user_id=chat.id,
        full_name=_full_name(chat),
        username=getattr(chat, "username", None),
        phone=getattr(chat, "phone", None),
    )
    direction = "outgoing" if bool(msg.out) else "incoming"
    created_at = msg.date if msg.date else datetime.now(timezone.utc)
    db.save_chat_message(
        customer_id=customer["id"],
        telegram_user_id=chat.id,
        message_id=msg.id,
        direction=direction,
        message_text=msg.raw_text or None,
        message_dt=created_at.date(),
        created_at=created_at,
    )


def register_userbot_handlers(client: TelegramClient, db: Database) -> None:
    @client.on(events.NewMessage(incoming=True))
    async def incoming_handler(event: events.NewMessage.Event) -> None:
        await save_message_from_event(db, event)

    @client.on(events.NewMessage(outgoing=True))
    async def outgoing_handler(event: events.NewMessage.Event) -> None:
        await save_message_from_event(db, event)


async def scan_recent_private_chats(client: TelegramClient, db: Database, days: int = 30) -> int:
    """Scan recent private dialogs and save messages. Returns saved/seen message count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    saved_count = 0

    async for dialog in client.iter_dialogs():
        if not dialog.is_user:
            continue
        entity = dialog.entity
        if not _is_valid_customer_user(entity):
            continue

        customer = db.upsert_customer(
            telegram_user_id=entity.id,
            full_name=_full_name(entity),
            username=getattr(entity, "username", None),
            phone=getattr(entity, "phone", None),
        )

        async for msg in client.iter_messages(entity, limit=1000):
            if not msg.date:
                continue
            msg_date = msg.date
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            if msg_date < cutoff:
                break
            if not msg.id:
                continue

            db.save_chat_message(
                customer_id=customer["id"],
                telegram_user_id=entity.id,
                message_id=msg.id,
                direction="outgoing" if bool(msg.out) else "incoming",
                message_text=msg.raw_text or None,
                message_dt=msg_date.date(),
                created_at=msg_date,
            )
            saved_count += 1

    return saved_count
