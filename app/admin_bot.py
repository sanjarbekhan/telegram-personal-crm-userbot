from __future__ import annotations

import asyncio
import html
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.config import Config
from app.db import Database
from app.lead_crm import (
    ResolveUsernameFunc,
    SendUserFunc,
    build_lead_router,
)
from app.scheduling import (
    MAX_SCHEDULE_RECIPIENTS,
    format_local_datetime,
    normalize_usernames,
    parse_local_datetime,
)

ScanFunc = Callable[[int], Awaitable[int]]
ScanContactsFunc = Callable[[], Awaitable[list[int]]]


class BroadcastStates(StatesGroup):
    waiting_date = State()
    waiting_message = State()
    waiting_confirm = State()


class SearchStates(StatesGroup):
    waiting_query = State()


class ScheduledMessageStates(StatesGroup):
    waiting_usernames = State()
    waiting_datetime = State()
    waiting_message = State()
    waiting_confirm = State()


VALID_STATUSES = {
    "new",
    "contacted",
    "interested",
    "follow_up",
    "paid",
    "rejected",
    "do_not_contact",
}

SCHEDULE_STATUS_LABELS = {
    "queued": "🕒 navbatda",
    "running": "🚀 yuborilyapti",
    "finished": "✅ tugagan",
    "cancelled": "🚫 bekor qilingan",
}


def is_admin(cfg: Config, user_id: int | None) -> bool:
    return bool(user_id and user_id == cfg.admin_telegram_id)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Lead qo‘shish"), KeyboardButton(text="📥 Leadlar")],
            [KeyboardButton(text="⚡ Kechikkanlar"), KeyboardButton(text="📈 CRM Dashboard")],
            [KeyboardButton(text="⏰ Xabar rejalash"), KeyboardButton(text="🗓 Rejadagi xabarlar")],
            [KeyboardButton(text="📨 Broadcast yuborish"), KeyboardButton(text="👥 Barchaga broadcast")],
            [KeyboardButton(text="📅 Sana bo‘yicha mijozlar"), KeyboardButton(text="🔍 Mijoz qidirish")],
            [KeyboardButton(text="📊 Hisobot"), KeyboardButton(text="⚙️ Yordam")],
        ],
        resize_keyboard=True,
    )


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ha, yuborish", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast_cancel")],
        ]
    )


def schedule_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Rejaga qo‘shish", callback_data="schedule_confirm")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="schedule_draft_cancel")],
        ]
    )


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    """A late/duplicate Telegram callback must not break the handler."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest:
        pass


def parse_date(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def customer_line(customer: dict) -> str:
    name = html.escape(customer.get("full_name") or "Nomsiz")
    username = customer.get("username")
    username_text = f"@{html.escape(username)}" if username else "username yo‘q"
    status = html.escape(customer.get("status") or "new")
    return (
        f"• <b>{name}</b> — {username_text} — "
        f"<code>{customer['telegram_user_id']}</code> — {status}"
    )


def schedule_list_keyboard(rows: list[dict]) -> InlineKeyboardMarkup | None:
    buttons = []
    for row in rows:
        if row.get("status") == "queued":
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🚫 Bekor qilish: {str(row['id'])[:8]}",
                        callback_data=f"schedule_cancel:{row['id']}",
                    )
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def create_dispatcher(
    cfg: Config,
    db: Database,
    scan_func: ScanFunc,
    scan_contacts_func: ScanContactsFunc,
    send_user_message: SendUserFunc,
    resolve_username: ResolveUsernameFunc,
) -> Dispatcher:
    router = Router()

    async def reject_non_admin(message: Message) -> bool:
        if is_admin(cfg, message.from_user.id if message.from_user else None):
            return False
        await message.answer("⛔ Ruxsat yo‘q.")
        return True

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.clear()
        await message.answer(
            "✅ <b>Telegram Personal CRM</b>\n\n"
            "Leadlarni bosqichma-bosqich boshqaring, professional tayyor javoblarni "
            "shaxsiy akkauntingizdan yuboring va javob bo‘lmasa xavfsiz follow-up ishlating.",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

    @router.message(Command("cancel"))
    async def cancel_cmd(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.clear()
        await message.answer("❌ Joriy amal bekor qilindi.", reply_markup=main_menu())

    @router.message(F.text == "⚙️ Yordam")
    @router.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        if await reject_non_admin(message):
            return
        await message.answer(
            "<b>Asosiy imkoniyatlar</b>\n\n"
            "🆕 <b>Lead qo‘shish</b> — username orqali yangi lead kartasi.\n"
            "📥 <b>Leadlar</b> — status, checklist, izoh va tezkor javoblar.\n"
            "⚡ <b>Kechikkanlar</b> — e’tibor talab qilayotgan leadlar.\n"
            "📈 <b>CRM Dashboard</b> — lead, to‘lov va nashr ko‘rsatkichlari.\n"
            "⏰ <b>Xabar rejalash</b> — username, vaqt va matn kiriting.\n"
            "🗓 <b>Rejadagi xabarlar</b> — holatini ko‘ring yoki oldindan bekor qiling.\n"
            "📨 <b>Broadcast</b> — tanlangan kundagi CRM mijozlariga yuboring.\n"
            "👥 <b>Barchaga broadcast</b> — barcha shaxsiy suhbatlardagi insonlarga yuboring.\n\n"
            "Buyruqlar:\n"
            "/scan 30 — oxirgi 30 kunlik private chatlarni bazaga tushirish\n"
            "/status TELEGRAM_ID follow_up — mijoz statusini o‘zgartirish\n"
            "/report — oxirgi broadcastlar\n"
            "/cancel — joriy amalni bekor qilish\n\n"
            f"Vaqt zonasi: <code>{html.escape(cfg.timezone)}</code>",
            parse_mode="HTML",
        )

    @router.message(Command("scan"))
    async def scan_cmd(message: Message) -> None:
        if await reject_non_admin(message):
            return
        parts = (message.text or "").split()
        days = cfg.scan_days
        if len(parts) > 1 and parts[1].isdigit():
            days = max(1, min(int(parts[1]), 365))
        await message.answer(f"🔄 Oxirgi {days} kunlik private chatlar skan qilinyapti...")

        async def _run_scan() -> None:
            try:
                count = await scan_func(days)
                await message.answer(f"✅ Skan tugadi. Saqlangan/ko‘rilgan xabarlar: {count}")
            except Exception as exc:
                await message.answer(
                    f"❌ Skan xatosi: {html.escape(str(exc))}",
                    parse_mode="HTML",
                )

        asyncio.create_task(_run_scan())

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        if await reject_non_admin(message):
            return
        parts = (message.text or "").split()
        if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in VALID_STATUSES:
            await message.answer(
                "Format: <code>/status TELEGRAM_ID follow_up</code>\n"
                f"Statuslar: <code>{', '.join(sorted(VALID_STATUSES))}</code>",
                parse_mode="HTML",
            )
            return
        db.set_customer_status(int(parts[1]), parts[2])
        if parts[2] == "do_not_contact":
            customer = db.get_customer_by_telegram_id(int(parts[1]))
            if customer and customer.get("is_lead"):
                db.update_lead_fields(
                    customer["id"],
                    pipeline_status="lost",
                    next_action_at=None,
                )
                db.cancel_customer_followups(
                    customer["id"],
                    reason="Admin boshqa yozmaslikni belgiladi",
                )
        await message.answer(
            f"✅ Status o‘zgardi: <code>{parts[1]}</code> → <b>{parts[2]}</b>",
            parse_mode="HTML",
        )

    @router.message(Command("report"))
    @router.message(F.text == "📊 Hisobot")
    async def report_cmd(message: Message) -> None:
        if await reject_non_admin(message):
            return
        rows = db.recent_broadcasts(limit=5)
        if not rows:
            await message.answer("Hali broadcast yo‘q.")
            return
        text = "📊 <b>Oxirgi broadcastlar</b>\n\n"
        for broadcast in rows:
            scope_text = (
                "Barcha kontaktlar"
                if broadcast.get("target_scope") == "all"
                else f"Sana: <code>{broadcast.get('target_date')}</code>"
            )
            text += (
                f"Qamrov: {scope_text}\n"
                f"Status: <b>{html.escape(broadcast.get('status') or '')}</b>\n"
                f"Jami: {broadcast.get('total_count')} | ✅ {broadcast.get('sent_count')} | "
                f"❌ {broadcast.get('failed_count')} | ⏭ {broadcast.get('skipped_count')}\n\n"
            )
        await message.answer(text, parse_mode="HTML")

    @router.message(F.text == "⏰ Xabar rejalash")
    async def schedule_start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.clear()
        await state.set_state(ScheduledMessageStates.waiting_usernames)
        await message.answer(
            "👤 Xabar yuboriladigan Telegram username(lar)ni kiriting.\n\n"
            "Bittadan ko‘p bo‘lsa vergul yoki yangi qatordan foydalaning.\n"
            "Masalan: <code>@ali_01, @vali_02</code>\n"
            f"Bir rejada ko‘pi bilan <b>{MAX_SCHEDULE_RECIPIENTS}</b> ta.",
            parse_mode="HTML",
        )

    @router.message(ScheduledMessageStates.waiting_usernames)
    async def schedule_usernames_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        usernames, invalid = normalize_usernames(message.text or "")
        if invalid:
            invalid_text = ", ".join(html.escape(value) for value in invalid[:10])
            await message.answer(
                f"❌ Noto‘g‘ri username: <code>{invalid_text}</code>\n"
                "Username 5–32 belgidan iborat bo‘lsin va harf bilan boshlansin.",
                parse_mode="HTML",
            )
            return
        if not usernames:
            await message.answer("❌ Kamida bitta to‘g‘ri username kiriting.")
            return
        if len(usernames) > MAX_SCHEDULE_RECIPIENTS:
            await message.answer(
                f"❌ Bitta rejada ko‘pi bilan {MAX_SCHEDULE_RECIPIENTS} ta username mumkin."
            )
            return

        await state.update_data(usernames=usernames)
        await state.set_state(ScheduledMessageStates.waiting_datetime)
        await message.answer(
            f"✅ {len(usernames)} ta username qabul qilindi.\n\n"
            f"🕒 Yuborish vaqtini <b>{html.escape(cfg.timezone)}</b> bo‘yicha kiriting:\n"
            "<code>2026-08-20 14:30</code>\n"
            "yoki soniyasi bilan: <code>2026-08-20 14:30:15</code>",
            parse_mode="HTML",
        )

    @router.message(ScheduledMessageStates.waiting_datetime)
    async def schedule_datetime_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        scheduled_at = parse_local_datetime(message.text or "", cfg.timezone)
        if scheduled_at is None:
            await message.answer(
                "❌ Vaqt formati noto‘g‘ri. Masalan: <code>2026-08-20 14:30</code>",
                parse_mode="HTML",
            )
            return
        if scheduled_at <= datetime.now(timezone.utc) + timedelta(seconds=15):
            await message.answer("❌ Hozirdan kamida 15 soniya keyingi vaqtni kiriting.")
            return

        await state.update_data(scheduled_at=scheduled_at.isoformat())
        await state.set_state(ScheduledMessageStates.waiting_message)
        await message.answer(
            "✍️ Endi yuboriladigan xabar matnini yozing.\n"
            "U aynan sizning shaxsiy Telegram akkauntingiz nomidan yuboriladi."
        )

    @router.message(ScheduledMessageStates.waiting_message)
    async def schedule_message_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        message_text = (message.text or "").strip()
        if not message_text:
            await message.answer("❌ Xabar matni bo‘sh bo‘lmasin.")
            return
        if len(message_text) > 4096:
            await message.answer("❌ Telegram matnli xabari 4096 belgidan oshmasin.")
            return

        data = await state.get_data()
        usernames = data["usernames"]
        scheduled_at = data["scheduled_at"]
        username_preview = ", ".join(f"@{html.escape(name)}" for name in usernames[:15])
        if len(usernames) > 15:
            username_preview += f" va yana {len(usernames) - 15} ta"

        await state.update_data(message_text=message_text)
        await state.set_state(ScheduledMessageStates.waiting_confirm)
        await message.answer(
            "⏰ <b>Rejadagi xabar preview</b>\n\n"
            f"Vaqt: <code>{format_local_datetime(scheduled_at, cfg.timezone)}</code> "
            f"({html.escape(cfg.timezone)})\n"
            f"Qabul qiluvchilar: <b>{len(usernames)}</b>\n"
            f"{username_preview}\n\n"
            f"Xabar:\n<blockquote>{html.escape(message_text)}</blockquote>\n\n"
            "Tasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=schedule_confirm_keyboard(),
        )

    @router.callback_query(F.data == "schedule_draft_cancel")
    async def schedule_draft_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await safe_callback_answer(callback, "Ruxsat yo‘q", show_alert=True)
            return
        await safe_callback_answer(callback)
        await state.clear()
        if callback.message:
            await callback.message.answer("❌ Rejalash bekor qilindi.", reply_markup=main_menu())

    @router.callback_query(F.data == "schedule_confirm")
    async def schedule_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await safe_callback_answer(callback, "Ruxsat yo‘q", show_alert=True)
            return
        await safe_callback_answer(callback, "Rejaga qo‘shilyapti…")
        data = await state.get_data()
        usernames = data.get("usernames") or []
        message_text = data.get("message_text")
        scheduled_at_raw = data.get("scheduled_at")
        if not usernames or not message_text or not scheduled_at_raw:
            await state.clear()
            if callback.message:
                await callback.message.answer(
                    "❌ Ma’lumot yetarli emas. Qaytadan boshlang.",
                    reply_markup=main_menu(),
                )
            return

        scheduled_at = datetime.fromisoformat(scheduled_at_raw)
        job = db.create_scheduled_message(
            usernames=usernames,
            message_text=message_text,
            scheduled_at=scheduled_at,
            timezone_name=cfg.timezone,
        )
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "✅ <b>Xabar rejaga qo‘shildi.</b>\n\n"
                f"ID: <code>{job['id']}</code>\n"
                f"Vaqt: <code>{format_local_datetime(job['scheduled_at'], cfg.timezone)}</code>\n"
                f"Qabul qiluvchilar: <b>{len(usernames)}</b>\n\n"
                "Belgilangan vaqtda shaxsiy akkauntingizdan yuborish boshlanadi.",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )

    @router.message(F.text == "🗓 Rejadagi xabarlar")
    async def scheduled_messages_list(message: Message) -> None:
        if await reject_non_admin(message):
            return
        rows = db.recent_scheduled_messages(limit=10)
        if not rows:
            await message.answer("Hali rejaga qo‘yilgan xabar yo‘q.")
            return

        text = "🗓 <b>Oxirgi rejadagi xabarlar</b>\n\n"
        for row in rows:
            status = SCHEDULE_STATUS_LABELS.get(
                row.get("status"),
                html.escape(row.get("status") or "noma’lum"),
            )
            text += (
                f"<code>{str(row['id'])[:8]}</code> — {status}\n"
                f"🕒 {format_local_datetime(row['scheduled_at'], cfg.timezone)}\n"
                f"Jami: {row.get('total_count', 0)} | ✅ {row.get('sent_count', 0)} | "
                f"❌ {row.get('failed_count', 0)} | ⏭ {row.get('skipped_count', 0)}\n\n"
            )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=schedule_list_keyboard(rows),
        )

    @router.callback_query(F.data.startswith("schedule_cancel:"))
    async def scheduled_message_cancel(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await safe_callback_answer(callback, "Ruxsat yo‘q", show_alert=True)
            return
        await safe_callback_answer(callback)
        scheduled_message_id = (callback.data or "").split(":", 1)[1]
        cancelled = db.cancel_scheduled_message(scheduled_message_id)
        if callback.message:
            if cancelled:
                await callback.message.answer(
                    f"🚫 Rejadagi xabar bekor qilindi: <code>{scheduled_message_id[:8]}</code>",
                    parse_mode="HTML",
                )
            else:
                await callback.message.answer(
                    "ℹ️ Bu xabar allaqachon boshlangan, tugagan yoki bekor qilingan."
                )

    @router.message(F.text == "📅 Sana bo‘yicha mijozlar")
    async def list_by_date_start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.set_state(BroadcastStates.waiting_date)
        await state.update_data(mode="list")
        await message.answer(
            "📅 Sanani kiriting. Format: <code>YYYY-MM-DD</code>",
            parse_mode="HTML",
        )

    @router.message(F.text == "📨 Broadcast yuborish")
    async def broadcast_start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.set_state(BroadcastStates.waiting_date)
        await state.update_data(mode="broadcast")
        await message.answer(
            "📅 Qaysi kundagi mijozlarga yozamiz? Format: <code>YYYY-MM-DD</code>",
            parse_mode="HTML",
        )

    @router.message(F.text == "👥 Barchaga broadcast")
    async def broadcast_all_start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.clear()
        await message.answer(
            "🔄 Telegramdagi shaxsiy suhbatlar tekshirilyapti...\n"
            "Faqat ism, username va Telegram ID olinadi; eski xabar matnlari import qilinmaydi."
        )
        try:
            imported_user_ids = await scan_contacts_func()
            customers = await asyncio.to_thread(
                db.get_broadcast_customers,
                imported_user_ids,
            )
        except Exception as exc:
            await message.answer(
                f"❌ Kontaktlarni yuklashda xato: {html.escape(str(exc))}",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )
            return

        if not customers:
            await message.answer(
                "Barchaga broadcast uchun mos kontakt topilmadi.",
                reply_markup=main_menu(),
            )
            return

        await state.update_data(
            target_scope="all",
            target_date=None,
            customers=customers,
        )
        await state.set_state(BroadcastStates.waiting_message)
        await message.answer(
            f"✅ Telegramdan <b>{len(imported_user_ids)}</b> ta shaxsiy suhbat tekshirildi.\n"
            f"Broadcast uchun <b>{len(customers)}</b> ta kontakt tayyor.\n\n"
            "Botlar, guruhlar, o‘chirilgan akkauntlar va <code>do_not_contact</code> "
            "kontaktlar chiqarib tashlandi.\n\n"
            "Endi yuboriladigan xabar matnini yozing.",
            parse_mode="HTML",
        )

    @router.message(BroadcastStates.waiting_date)
    async def broadcast_date_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        target_date = parse_date(message.text or "")
        if not target_date:
            await message.answer(
                "❌ Sana noto‘g‘ri. Masalan: <code>2026-06-18</code>",
                parse_mode="HTML",
            )
            return

        customers = db.get_customers_by_date(target_date)
        data = await state.get_data()
        mode = data.get("mode")

        if mode == "list":
            await state.clear()
            if not customers:
                await message.answer(
                    f"{target_date} kuni mijoz topilmadi.",
                    reply_markup=main_menu(),
                )
                return
            lines = [customer_line(customer) for customer in customers[:30]]
            more = "" if len(customers) <= 30 else f"\n... yana {len(customers) - 30} ta bor."
            await message.answer(
                f"📅 <code>{target_date}</code> kuni topildi: <b>{len(customers)}</b> mijoz\n\n"
                + "\n".join(lines)
                + more,
                parse_mode="HTML",
                reply_markup=main_menu(),
            )
            return

        if not customers:
            await state.clear()
            await message.answer(
                f"{target_date} kuni broadcast uchun mijoz topilmadi.",
                reply_markup=main_menu(),
            )
            return

        await state.update_data(
            target_scope="date",
            target_date=target_date,
            customers=customers,
        )
        await state.set_state(BroadcastStates.waiting_message)
        await message.answer(
            f"✅ <code>{target_date}</code> kuni <b>{len(customers)}</b> ta mijoz topildi.\n\n"
            "Endi yuboriladigan xabar matnini yozing.",
            parse_mode="HTML",
        )

    @router.message(BroadcastStates.waiting_message)
    async def broadcast_message_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        message_text = (message.text or "").strip()
        if not message_text:
            await message.answer("❌ Xabar matni bo‘sh bo‘lmasin.")
            return
        data = await state.get_data()
        target_scope = data.get("target_scope", "date")
        target_date = data.get("target_date")
        customers = data["customers"]
        min_delay = db.get_setting_int("min_delay_seconds", cfg.min_delay_seconds)
        max_delay = db.get_setting_int("max_delay_seconds", cfg.max_delay_seconds)
        avg_delay = (min_delay + max_delay) / 2
        estimated_minutes = round((len(customers) * avg_delay) / 60, 1)

        scope_text = (
            "Barcha mos shaxsiy kontaktlar"
            if target_scope == "all"
            else f"{target_date} kundagi mijozlar"
        )
        await state.update_data(message_text=message_text)
        await state.set_state(BroadcastStates.waiting_confirm)
        await message.answer(
            "📨 <b>Broadcast preview</b>\n\n"
            f"Qamrov: <b>{html.escape(scope_text)}</b>\n"
            f"Mijozlar soni: <b>{len(customers)}</b>\n"
            f"Taxminiy vaqt: <b>{estimated_minutes}</b> daqiqa\n\n"
            f"Xabar:\n<blockquote>{html.escape(message_text)}</blockquote>\n\n"
            "Tasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=broadcast_confirm_keyboard(),
        )

    @router.callback_query(F.data == "broadcast_cancel")
    async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await safe_callback_answer(callback, "Ruxsat yo‘q", show_alert=True)
            return
        await safe_callback_answer(callback)
        await state.clear()
        if callback.message:
            await callback.message.answer("❌ Bekor qilindi.", reply_markup=main_menu())

    @router.callback_query(F.data == "broadcast_confirm")
    async def broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await safe_callback_answer(callback, "Ruxsat yo‘q", show_alert=True)
            return
        await safe_callback_answer(callback, "Navbatga qo‘shilyapti…")
        data = await state.get_data()
        target_scope = data.get("target_scope", "date")
        target_date = data.get("target_date")
        message_text = data.get("message_text")
        customers = data.get("customers") or []
        missing_target = target_scope == "date" and not target_date
        if missing_target or not message_text or not customers:
            if callback.message:
                await callback.message.answer(
                    "❌ Ma’lumot yetarli emas. Qaytadan boshlang.",
                    reply_markup=main_menu(),
                )
            await state.clear()
            return
        broadcast = await asyncio.to_thread(
            db.create_broadcast,
            target_date,
            message_text,
            customers,
            target_scope=target_scope,
        )
        await state.clear()
        if callback.message:
            scope_text = (
                "barcha mos kontaktlar"
                if target_scope == "all"
                else f"{target_date} kundagi mijozlar"
            )
            await callback.message.answer(
                "✅ Broadcast navbatga qo‘shildi.\n"
                f"ID: <code>{broadcast['id']}</code>\n"
                f"Qamrov: <b>{html.escape(scope_text)}</b>\n"
                f"Mijozlar: <b>{len(customers)}</b>\n\n"
                "Sender worker ularni shaxsiy akkauntingizdan navbat bilan yuboradi.",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )

    @router.message(F.text == "🔍 Mijoz qidirish")
    async def search_start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.set_state(SearchStates.waiting_query)
        await message.answer("🔍 Ism, username yoki Telegram ID kiriting.")

    @router.message(SearchStates.waiting_query)
    async def search_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        rows = db.search_customers(message.text or "", limit=10)
        await state.clear()
        if not rows:
            await message.answer("Mijoz topilmadi.", reply_markup=main_menu())
            return
        await message.answer(
            "\n".join(customer_line(customer) for customer in rows),
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(
        build_lead_router(
            cfg,
            db,
            send_user_message,
            resolve_username,
        )
    )
    dp.include_router(router)
    return dp
