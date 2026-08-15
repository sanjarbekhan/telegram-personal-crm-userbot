from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from app.config import Config
from app.db import Database
from app.lead_crm import dashboard_text


async def daily_dashboard_loop(bot: Bot, db: Database, cfg: Config) -> None:
    try:
        local_zone = ZoneInfo(cfg.timezone)
    except ZoneInfoNotFoundError:
        local_zone = ZoneInfo("UTC")

    while True:
        try:
            now = datetime.now(local_zone)
            report_date = now.date().isoformat()
            last_sent = await asyncio.to_thread(
                db.get_setting,
                "last_daily_dashboard_date",
                "",
            )
            if now.hour >= cfg.daily_report_hour and last_sent != report_date:
                data = await asyncio.to_thread(db.get_lead_dashboard, cfg.timezone)
                await bot.send_message(
                    cfg.admin_telegram_id,
                    "🌙 <b>Kunlik CRM hisoboti</b>\n\n"
                    + dashboard_text(data).replace(
                        "📈 <b>CRM dashboard</b>\n\n",
                        "",
                        1,
                    ),
                    parse_mode="HTML",
                )
                await asyncio.to_thread(
                    db.set_setting,
                    "last_daily_dashboard_date",
                    report_date,
                )
        except Exception:
            # Daily reporting must never stop polling or the sender worker.
            pass
        await asyncio.sleep(60)
