from __future__ import annotations

import asyncio
import html
from datetime import datetime
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
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

ScanFunc = Callable[[int], Awaitable[int]]


class BroadcastStates(StatesGroup):
    waiting_date = State()
    waiting_message = State()
    waiting_confirm = State()


class SearchStates(StatesGroup):
    waiting_query = State()


VALID_STATUSES = {
    "new",
    "contacted",
    "interested",
    "follow_up",
    "paid",
    "rejected",
    "do_not_contact",
}


def is_admin(cfg: Config, user_id: int | None) -> bool:
    return bool(user_id and user_id == cfg.admin_telegram_id)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📨 Broadcast yuborish")],
            [KeyboardButton(text="📅 Sana bo‘yicha mijozlar"), KeyboardButton(text="🔍 Mijoz qidirish")],
            [KeyboardButton(text="📊 Hisobot"), KeyboardButton(text="⚙️ Yordam")],
        ],
        resize_keyboard=True,
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ha, yuborish", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast_cancel")],
        ]
    )


def parse_date(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def customer_line(c: dict) -> str:
    name = html.escape(c.get("full_name") or "Nomsiz")
    username = c.get("username")
    username_text = f"@{html.escape(username)}" if username else "username yo‘q"
    status = html.escape(c.get("status") or "new")
    return f"• <b>{name}</b> — {username_text} — <code>{c['telegram_user_id']}</code> — {status}"


def create_dispatcher(cfg: Config, db: Database, scan_func: ScanFunc) -> Dispatcher:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        await state.clear()
        await message.answer(
            "✅ Telegram Personal CRM admin panel.\n\n"
            "Sana tanlab, o‘sha kuni yozishgan mijozlarga shaxsiy akkaunt orqali follow-up yuborishingiz mumkin.",
            reply_markup=main_menu(),
        )

    @router.message(F.text == "⚙️ Yordam")
    @router.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        await message.answer(
            "Buyruqlar:\n"
            "/scan 30 — oxirgi 30 kunlik private chatlarni bazaga tushirish\n"
            "/status TELEGRAM_ID follow_up — mijoz statusini o‘zgartirish\n"
            "/report — oxirgi broadcastlar\n\n"
            "Sana formati: <code>YYYY-MM-DD</code>\n"
            "Masalan: <code>2026-06-18</code>",
            parse_mode="HTML",
        )

    @router.message(Command("scan"))
    async def scan_cmd(message: Message) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
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
            except Exception as e:
                await message.answer(f"❌ Skan xatosi: {html.escape(str(e))}", parse_mode="HTML")

        asyncio.create_task(_run_scan())

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
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
        await message.answer(f"✅ Status o‘zgardi: <code>{parts[1]}</code> → <b>{parts[2]}</b>", parse_mode="HTML")

    @router.message(Command("report"))
    @router.message(F.text == "📊 Hisobot")
    async def report_cmd(message: Message) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        rows = db.recent_broadcasts(limit=5)
        if not rows:
            await message.answer("Hali broadcast yo‘q.")
            return
        text = "📊 <b>Oxirgi broadcastlar</b>\n\n"
        for b in rows:
            text += (
                f"Sana: <code>{b.get('target_date')}</code>\n"
                f"Status: <b>{html.escape(b.get('status') or '')}</b>\n"
                f"Jami: {b.get('total_count')} | ✅ {b.get('sent_count')} | ❌ {b.get('failed_count')} | ⏭ {b.get('skipped_count')}\n\n"
            )
        await message.answer(text, parse_mode="HTML")

    @router.message(F.text == "📅 Sana bo‘yicha mijozlar")
    async def list_by_date_start(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        await state.set_state(BroadcastStates.waiting_date)
        await state.update_data(mode="list")
        await message.answer("📅 Sanani kiriting. Format: <code>YYYY-MM-DD</code>", parse_mode="HTML")

    @router.message(F.text == "📨 Broadcast yuborish")
    async def broadcast_start(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        await state.set_state(BroadcastStates.waiting_date)
        await state.update_data(mode="broadcast")
        await message.answer("📅 Qaysi kundagi mijozlarga yozamiz? Format: <code>YYYY-MM-DD</code>", parse_mode="HTML")

    @router.message(BroadcastStates.waiting_date)
    async def broadcast_date_received(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        target_date = parse_date(message.text or "")
        if not target_date:
            await message.answer("❌ Sana noto‘g‘ri. Masalan: <code>2026-06-18</code>", parse_mode="HTML")
            return

        customers = db.get_customers_by_date(target_date)
        data = await state.get_data()
        mode = data.get("mode")

        if mode == "list":
            await state.clear()
            if not customers:
                await message.answer(f"{target_date} kuni mijoz topilmadi.", reply_markup=main_menu())
                return
            lines = [customer_line(c) for c in customers[:30]]
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
            await message.answer(f"{target_date} kuni broadcast uchun mijoz topilmadi.", reply_markup=main_menu())
            return

        await state.update_data(target_date=target_date, customers=customers)
        await state.set_state(BroadcastStates.waiting_message)
        await message.answer(
            f"✅ <code>{target_date}</code> kuni <b>{len(customers)}</b> ta mijoz topildi.\n\n"
            "Endi yuboriladigan xabar matnini yozing.",
            parse_mode="HTML",
        )

    @router.message(BroadcastStates.waiting_message)
    async def broadcast_message_received(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Xabar matni bo‘sh bo‘lmasin.")
            return
        data = await state.get_data()
        target_date = data["target_date"]
        customers = data["customers"]
        min_delay = db.get_setting_int("min_delay_seconds", cfg.min_delay_seconds)
        max_delay = db.get_setting_int("max_delay_seconds", cfg.max_delay_seconds)
        avg_delay = (min_delay + max_delay) / 2
        estimated_minutes = round((len(customers) * avg_delay) / 60, 1)

        await state.update_data(message_text=text)
        await state.set_state(BroadcastStates.waiting_confirm)
        await message.answer(
            "📨 <b>Broadcast preview</b>\n\n"
            f"Sana: <code>{target_date}</code>\n"
            f"Mijozlar soni: <b>{len(customers)}</b>\n"
            f"Taxminiy vaqt: <b>{estimated_minutes}</b> daqiqa\n\n"
            f"Xabar:\n<blockquote>{html.escape(text)}</blockquote>\n\n"
            "Tasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=confirm_keyboard(),
        )

    @router.callback_query(F.data == "broadcast_cancel")
    async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await callback.answer("Ruxsat yo‘q", show_alert=True)
            return
        await state.clear()
        await callback.message.answer("❌ Bekor qilindi.", reply_markup=main_menu())
        await callback.answer()

    @router.callback_query(F.data == "broadcast_confirm")
    async def broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id if callback.from_user else None):
            await callback.answer("Ruxsat yo‘q", show_alert=True)
            return
        data = await state.get_data()
        target_date = data.get("target_date")
        message_text = data.get("message_text")
        customers = data.get("customers") or []
        if not target_date or not message_text or not customers:
            await callback.message.answer("❌ Ma’lumot yetarli emas. Qaytadan boshlang.", reply_markup=main_menu())
            await state.clear()
            await callback.answer()
            return
        broadcast = db.create_broadcast(target_date, message_text, customers)
        await state.clear()
        await callback.message.answer(
            "✅ Broadcast navbatga qo‘shildi.\n"
            f"ID: <code>{broadcast['id']}</code>\n"
            f"Mijozlar: <b>{len(customers)}</b>\n\n"
            "Sender worker ularni sekin-sekin shaxsiy akkauntingizdan yuboradi.",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        await callback.answer("Queued")

    @router.message(F.text == "🔍 Mijoz qidirish")
    async def search_start(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        await state.set_state(SearchStates.waiting_query)
        await message.answer("🔍 Ism, username yoki Telegram ID kiriting.")

    @router.message(SearchStates.waiting_query)
    async def search_received(message: Message, state: FSMContext) -> None:
        if not is_admin(cfg, message.from_user.id if message.from_user else None):
            await message.answer("⛔ Ruxsat yo‘q.")
            return
        rows = db.search_customers(message.text or "", limit=10)
        await state.clear()
        if not rows:
            await message.answer("Mijoz topilmadi.", reply_markup=main_menu())
            return
        await message.answer("\n".join(customer_line(c) for c in rows), parse_mode="HTML", reply_markup=main_menu())

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    return dp
