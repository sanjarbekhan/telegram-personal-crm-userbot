from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from aiogram import Bot
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import User

from app.config import Config
from app.db import Database


async def db_call(func, /, *args, **kwargs):
    """Keep synchronous Supabase HTTP calls off aiogram's event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def notify_admin(bot: Bot, cfg: Config, text: str) -> None:
    try:
        await bot.send_message(cfg.admin_telegram_id, text)
    except Exception:
        pass


async def _safe_delay(db: Database, cfg: Config) -> None:
    min_delay = await db_call(
        db.get_setting_int,
        "min_delay_seconds",
        cfg.min_delay_seconds,
    )
    max_delay = await db_call(
        db.get_setting_int,
        "max_delay_seconds",
        cfg.max_delay_seconds,
    )
    if max_delay < min_delay:
        max_delay = min_delay
    await asyncio.sleep(random.randint(min_delay, max_delay))


async def _process_due_scheduled_message(
    client: TelegramClient,
    admin_bot: Bot,
    db: Database,
    cfg: Config,
) -> bool:
    job = await db_call(db.get_due_scheduled_message)
    if not job:
        return False

    recipient = await db_call(db.get_next_scheduled_recipient, job["id"])
    if not recipient:
        await db_call(db.recalc_scheduled_counts, job["id"])
        return True

    await db_call(db.mark_scheduled_message_running, job["id"])
    await db_call(db.update_scheduled_recipient, recipient["id"], "processing")
    username = recipient["username"]

    try:
        entity = await client.get_entity(f"@{username}")
        if not isinstance(entity, User):
            raise ValueError("Username shaxsiy Telegram foydalanuvchisiga tegishli emas")
        if entity.bot or entity.deleted or entity.is_self:
            raise ValueError("Bot, o'chirilgan yoki o'z akkauntingizga yuborib bo'lmaydi")
        await client.send_message(entity, job["message_text"])
        await db_call(
            db.update_scheduled_recipient,
            recipient["id"],
            "sent",
            telegram_user_id=entity.id,
        )
    except FloodWaitError as exc:
        await db_call(db.update_scheduled_recipient, recipient["id"], "pending")
        await notify_admin(
            admin_bot,
            cfg,
            f"⏳ Telegram FloodWait: {exc.seconds} sekund. Rejadagi xabar kutadi.",
        )
        await asyncio.sleep(min(exc.seconds + 5, 600))
        return True
    except Exception as exc:
        await db_call(
            db.update_scheduled_recipient,
            recipient["id"],
            "failed",
            error_text=str(exc),
        )

    counts = await db_call(db.recalc_scheduled_counts, job["id"])
    refreshed = await db_call(db.get_scheduled_message, job["id"])
    if refreshed and refreshed.get("status") == "finished":
        await notify_admin(
            admin_bot,
            cfg,
            "⏰ Rejadagi xabar yakunlandi.\n"
            f"✅ Yuborildi: {counts['sent_count']}\n"
            f"❌ Xato: {counts['failed_count']}\n"
            f"⏭ O‘tkazildi: {counts['skipped_count']}",
        )
    else:
        await _safe_delay(db, cfg)
    return True


async def _process_broadcast(
    client: TelegramClient,
    admin_bot: Bot,
    db: Database,
    cfg: Config,
) -> bool:
    log = await db_call(db.get_next_pending_log)
    if not log:
        return False

    broadcast = await db_call(db.get_broadcast, log["broadcast_id"])
    if not broadcast or broadcast.get("status") == "cancelled":
        await db_call(
            db.update_log,
            log["id"],
            "skipped",
            "Broadcast cancelled or not found",
        )
        return True

    customer = await db_call(db.get_customer_by_id, log["customer_id"])
    if not customer:
        await db_call(db.update_log, log["id"], "skipped", "Customer not found")
        await db_call(db.recalc_broadcast_counts, log["broadcast_id"])
        return True

    if customer.get("status") == "do_not_contact":
        await db_call(
            db.update_log,
            log["id"],
            "skipped",
            "Customer is do_not_contact",
        )
        await db_call(db.recalc_broadcast_counts, log["broadcast_id"])
        return True

    await db_call(db.mark_broadcast_running, log["broadcast_id"])
    await db_call(db.update_log, log["id"], "processing")

    try:
        await client.send_message(
            int(log["telegram_user_id"]),
            broadcast["message_text"],
        )
        await db_call(db.update_log, log["id"], "sent")
    except FloodWaitError as exc:
        await db_call(db.update_log, log["id"], "pending")
        await notify_admin(
            admin_bot,
            cfg,
            f"⏳ FloodWait: {exc.seconds} sekund kutyapman.",
        )
        await asyncio.sleep(min(exc.seconds + 5, 600))
        return True
    except Exception as exc:
        await db_call(db.update_log, log["id"], "failed", str(exc))

    counts = await db_call(db.recalc_broadcast_counts, log["broadcast_id"])
    refreshed = await db_call(db.get_broadcast, log["broadcast_id"])
    if refreshed and refreshed.get("status") == "finished":
        await notify_admin(
            admin_bot,
            cfg,
            "📊 Broadcast tugadi:\n"
            f"Sana: {refreshed.get('target_date')}\n"
            f"Jami: {refreshed.get('total_count')}\n"
            f"✅ Yuborildi: {counts['sent_count']}\n"
            f"❌ Xato: {counts['failed_count']}\n"
            f"⏭ O‘tkazildi: {counts['skipped_count']}\n"
            f"Tugagan vaqt: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        )
    await _safe_delay(db, cfg)
    return True


async def sender_loop(
    client: TelegramClient,
    bot: Bot,
    db: Database,
    cfg: Config,
) -> None:
    await notify_admin(bot, cfg, "✅ Sender worker ishga tushdi.")

    while True:
        try:
            daily_limit = await db_call(
                db.get_setting_int,
                "daily_send_limit",
                cfg.daily_send_limit,
            )
            if await db_call(db.get_daily_sent_count) >= daily_limit:
                await asyncio.sleep(60)
                continue

            # Rejadagi xabarlar vaqtga bog'liq, shuning uchun birinchi tekshiriladi.
            if await _process_due_scheduled_message(client, bot, db, cfg):
                continue
            if await _process_broadcast(client, bot, db, cfg):
                continue
            await asyncio.sleep(min(cfg.poll_seconds, cfg.schedule_poll_seconds))
        except Exception as exc:
            await notify_admin(bot, cfg, f"⚠️ Sender worker xatosi: {exc}")
            await asyncio.sleep(15)
