from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import Bot
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User

from app.contact_import import scan_private_contacts
from app.config import Config
from app.db import Database
from app.retry import to_thread_with_retry


def build_user_client(cfg: Config) -> TelegramClient:
    return TelegramClient(
        StringSession(cfg.telethon_session),
        cfg.api_id,
        cfg.api_hash,
    )


def _full_name(user: User) -> str:
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join(part for part in parts if part) or "Unknown"


def _is_valid_customer_user(user: Any) -> bool:
    return bool(
        isinstance(user, User)
        and not getattr(user, "bot", False)
        and not getattr(user, "is_self", False)
        and not getattr(user, "deleted", False)
    )


async def save_message_from_event(
    db: Database,
    event: events.NewMessage.Event,
) -> tuple[dict[str, Any] | None, int]:
    if not event.is_private:
        return None, 0

    chat = await event.get_chat()
    if not _is_valid_customer_user(chat):
        return None, 0

    message = event.message
    customer = await to_thread_with_retry(
        db.upsert_customer,
        chat.id,
        _full_name(chat),
        getattr(chat, "username", None),
        getattr(chat, "phone", None),
    )
    direction = "outgoing" if bool(message.out) else "incoming"
    created_at = message.date or datetime.now(timezone.utc)
    await to_thread_with_retry(
        db.save_chat_message,
        customer["id"],
        chat.id,
        message.id,
        direction,
        message.raw_text or None,
        created_at.date(),
        created_at,
    )

    if direction == "incoming":
        return await to_thread_with_retry(db.handle_incoming_lead_reply, chat.id)
    return await to_thread_with_retry(db.get_customer_by_id, customer["id"]), 0


def register_userbot_handlers(
    client: TelegramClient,
    db: Database,
    admin_bot: Bot | None = None,
    cfg: Config | None = None,
) -> None:
    @client.on(events.NewMessage(incoming=True))
    async def incoming_handler(event: events.NewMessage.Event) -> None:
        customer, cancelled = await save_message_from_event(db, event)
        if (
            not customer
            or not customer.get("is_lead")
            or not admin_bot
            or not cfg
        ):
            return
        username = customer.get("username")
        username_text = f"@{html.escape(username)}" if username else "username yo‘q"
        message_text = html.escape((event.message.raw_text or "[media]")[:800])
        cancelled_text = (
            f"\n⛔ Bekor qilingan follow-up: <b>{cancelled}</b>"
            if cancelled
            else ""
        )
        try:
            await admin_bot.send_message(
                cfg.admin_telegram_id,
                "💬 <b>Leaddan javob keldi</b>\n\n"
                f"👤 {html.escape(customer.get('full_name') or 'Nomsiz')}\n"
                f"{username_text} · <code>{customer['telegram_user_id']}</code>\n\n"
                f"<blockquote>{message_text}</blockquote>"
                f"{cancelled_text}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    @client.on(events.NewMessage(outgoing=True))
    async def outgoing_handler(event: events.NewMessage.Event) -> None:
        await save_message_from_event(db, event)


async def scan_recent_private_chats(
    client: TelegramClient,
    db: Database,
    days: int = 30,
) -> int:
    """Scan recent private dialogs and save messages without blocking aiogram."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    saved_count = 0

    async for dialog in client.iter_dialogs():
        if not dialog.is_user:
            continue
        entity = dialog.entity
        if not _is_valid_customer_user(entity):
            continue

        customer = await to_thread_with_retry(
            db.upsert_customer,
            entity.id,
            _full_name(entity),
            getattr(entity, "username", None),
            getattr(entity, "phone", None),
        )

        async for message in client.iter_messages(entity, limit=1000):
            if not message.date:
                continue
            message_date = message.date
            if message_date.tzinfo is None:
                message_date = message_date.replace(tzinfo=timezone.utc)
            if message_date < cutoff:
                break
            if not message.id:
                continue

            await to_thread_with_retry(
                db.save_chat_message,
                customer["id"],
                entity.id,
                message.id,
                "outgoing" if bool(message.out) else "incoming",
                message.raw_text or None,
                message_date.date(),
                message_date,
                False,
            )
            saved_count += 1

    return saved_count
