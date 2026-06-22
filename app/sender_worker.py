from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from aiogram import Bot
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from app.config import Config
from app.db import Database


async def notify_admin(bot: Bot, cfg: Config, text: str) -> None:
    try:
        await bot.send_message(cfg.admin_telegram_id, text)
    except Exception:
        # Avoid crashing the sender if Telegram Bot API notification fails.
        pass


async def sender_loop(client: TelegramClient, bot: Bot, db: Database, cfg: Config) -> None:
    await notify_admin(bot, cfg, "✅ Sender worker ishga tushdi.")

    while True:
        try:
            daily_limit = db.get_setting_int("daily_send_limit", cfg.daily_send_limit)
            sent_today = db.get_daily_sent_count()
            if sent_today >= daily_limit:
                await asyncio.sleep(60)
                continue

            log = db.get_next_pending_log()
            if not log:
                await asyncio.sleep(cfg.poll_seconds)
                continue

            broadcast = db.get_broadcast(log["broadcast_id"])
            if not broadcast or broadcast.get("status") == "cancelled":
                db.update_log(log["id"], "skipped", "Broadcast cancelled or not found")
                continue

            customer = db.get_customer_by_id(log["customer_id"])
            if not customer:
                db.update_log(log["id"], "skipped", "Customer not found")
                db.recalc_broadcast_counts(log["broadcast_id"])
                continue

            if customer.get("status") == "do_not_contact":
                db.update_log(log["id"], "skipped", "Customer is do_not_contact")
                db.recalc_broadcast_counts(log["broadcast_id"])
                continue

            db.mark_broadcast_running(log["broadcast_id"])
            db.update_log(log["id"], "processing")

            try:
                await client.send_message(int(log["telegram_user_id"]), broadcast["message_text"])
                db.update_log(log["id"], "sent")
            except FloodWaitError as e:
                # Respect Telegram flood wait. For very long waits, stop this item and report.
                if e.seconds <= 600:
                    await notify_admin(bot, cfg, f"⏳ FloodWait: {e.seconds} sekund kutyapman.")
                    await asyncio.sleep(e.seconds + 5)
                    try:
                        await client.send_message(int(log["telegram_user_id"]), broadcast["message_text"])
                        db.update_log(log["id"], "sent")
                    except Exception as retry_error:
                        db.update_log(log["id"], "failed", str(retry_error))
                else:
                    db.update_log(log["id"], "failed", f"FloodWait too long: {e.seconds} seconds")
                    await notify_admin(bot, cfg, f"⚠️ FloodWait juda uzun: {e.seconds} sekund. Yuborish to‘xtatildi.")
            except Exception as send_error:
                db.update_log(log["id"], "failed", str(send_error))

            counts = db.recalc_broadcast_counts(log["broadcast_id"])
            refreshed = db.get_broadcast(log["broadcast_id"])
            if refreshed and refreshed.get("status") == "finished":
                await notify_admin(
                    bot,
                    cfg,
                    "📊 Broadcast tugadi:\n"
                    f"Sana: {refreshed.get('target_date')}\n"
                    f"Jami: {refreshed.get('total_count')}\n"
                    f"✅ Yuborildi: {counts['sent_count']}\n"
                    f"❌ Xato: {counts['failed_count']}\n"
                    f"⏭ O‘tkazildi: {counts['skipped_count']}\n"
                    f"Tugagan vaqt: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                )

            min_delay = db.get_setting_int("min_delay_seconds", cfg.min_delay_seconds)
            max_delay = db.get_setting_int("max_delay_seconds", cfg.max_delay_seconds)
            if max_delay < min_delay:
                max_delay = min_delay
            await asyncio.sleep(random.randint(min_delay, max_delay))

        except Exception as loop_error:
            await notify_admin(bot, cfg, f"⚠️ Sender worker xatosi: {loop_error}")
            await asyncio.sleep(15)
