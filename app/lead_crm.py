from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Config
from app.db import Database
from app.lead_templates import (
    CHECKLIST_FIELDS,
    PIPELINE_LABELS,
    TEMPLATE_LABELS,
    available_quick_replies,
    build_followup_plan,
    render_template,
)
from app.scheduling import format_local_datetime, normalize_usernames


SendUserFunc = Callable[[int, str], Awaitable[None]]
ResolveUsernameFunc = Callable[[str], Awaitable[dict[str, Any]]]

CHECKLIST_CALLBACKS = {
    "app": "application_complete",
    "photo": "photo_received",
    "docs": "documents_received",
    "consent": "consent_received",
}

STAGE_ORDER = [
    "new",
    "contacted",
    "interested",
    "questionnaire",
    "awaiting_documents",
    "awaiting_payment",
    "paid",
    "drafting",
    "review",
    "published",
    "lost",
]


class AddLeadStates(StatesGroup):
    waiting_username = State()


class LeadNoteStates(StatesGroup):
    waiting_note = State()


class LeadInstagramStates(StatesGroup):
    waiting_username = State()


class LeadPublishedStates(StatesGroup):
    waiting_url = State()


async def db_call(func, /, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest:
        pass


def is_admin(cfg: Config, user_id: int | None) -> bool:
    return bool(user_id and user_id == cfg.admin_telegram_id)


def format_optional_time(value: str | None, cfg: Config) -> str:
    if not value:
        return "—"
    return format_local_datetime(value, cfg.timezone)


def lead_profile_text(customer: dict[str, Any], cfg: Config) -> str:
    checklist = []
    for field, label in CHECKLIST_FIELDS.items():
        checklist.append(f"{'✅' if customer.get(field) else '❌'} {label}")
    checklist.append(
        f"{'✅' if customer.get('instagram_username') else '❌'} Instagram"
    )
    checklist.append(
        f"{'✅' if customer.get('payment_status') == 'paid' else '❌'} To‘lov"
    )

    username = customer.get("username")
    username_text = f"@{html.escape(username)}" if username else "username yo‘q"
    status = PIPELINE_LABELS.get(
        customer.get("pipeline_status") or "new",
        html.escape(customer.get("pipeline_status") or "new"),
    )
    notes = html.escape(customer.get("notes") or "—")
    return (
        f"👤 <b>{html.escape(customer.get('full_name') or 'Nomsiz lead')}</b>\n"
        f"{username_text} · <code>{customer['telegram_user_id']}</code>\n\n"
        f"Bosqich: <b>{status}</b>\n"
        f"Manba: <code>{html.escape(customer.get('lead_source') or 'manual')}</code>\n"
        f"Oxirgi kiruvchi: <code>{format_optional_time(customer.get('last_inbound_at'), cfg)}</code>\n"
        f"Oxirgi chiquvchi: <code>{format_optional_time(customer.get('last_outbound_at'), cfg)}</code>\n"
        f"Keyingi amal: <code>{format_optional_time(customer.get('next_action_at'), cfg)}</code>\n\n"
        "<b>Checklist</b>\n"
        + "\n".join(checklist)
        + f"\n\n<b>Izoh</b>\n{notes}"
    )


def lead_profile_keyboard(customer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Birinchi xabar + 3 follow-up",
                    callback_data=f"lw:{customer_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Tayyor javoblar",
                    callback_data=f"lq:{customer_id}",
                ),
                InlineKeyboardButton(
                    text="📌 Bosqich",
                    callback_data=f"lst:{customer_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Checklist",
                    callback_data=f"lcl:{customer_id}",
                ),
                InlineKeyboardButton(
                    text="📝 Izoh",
                    callback_data=f"ln:{customer_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Nashr havolasi",
                    callback_data=f"lpub:{customer_id}",
                ),
                InlineKeyboardButton(
                    text="🚫 Boshqa yozmang",
                    callback_data=f"ldnc:{customer_id}",
                ),
            ],
        ]
    )


def lead_list_keyboard(rows: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        f"{PIPELINE_LABELS.get(row.get('pipeline_status') or 'new', 'Lead')} · "
                        f"{(row.get('full_name') or row.get('username') or row['telegram_user_id'])}"
                    )[:60],
                    callback_data=f"lp:{row['id']}",
                )
            ]
            for row in rows
        ]
    )


def stage_keyboard(customer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=PIPELINE_LABELS[stage],
                    callback_data=f"ls:{customer_id}:{stage}",
                )
            ]
            for stage in STAGE_ORDER
        ]
    )


def checklist_keyboard(customer: dict[str, Any]) -> InlineKeyboardMarkup:
    buttons = []
    for short, field in CHECKLIST_CALLBACKS.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{'✅' if customer.get(field) else '⬜'} {CHECKLIST_FIELDS[field]}",
                    callback_data=f"lct:{customer['id']}:{short}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text=(
                    f"✅ Instagram: @{customer['instagram_username']}"
                    if customer.get("instagram_username")
                    else "⬜ Instagram kiritish"
                ),
                callback_data=f"li:{customer['id']}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quick_replies_keyboard(
    customer: dict[str, Any],
    cfg: Config,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=TEMPLATE_LABELS[key],
                    callback_data=f"lr:{customer['id']}:{key}",
                )
            ]
            for key in available_quick_replies(customer, cfg)
        ]
    )


def dashboard_text(data: dict[str, Any]) -> str:
    stages = data.get("stages") or {}
    stage_lines = [
        f"{PIPELINE_LABELS.get(stage, stage)}: <b>{count}</b>"
        for stage, count in stages.items()
        if count
    ]
    return (
        "📈 <b>CRM dashboard</b>\n\n"
        f"Jami leadlar: <b>{data.get('total', 0)}</b>\n"
        f"Bugun qo‘shildi: <b>{data.get('new_today', 0)}</b>\n"
        f"Kechikkan amallar: <b>{data.get('overdue', 0)}</b>\n"
        f"To‘lov qilganlar: <b>{data.get('paid', 0)}</b>\n"
        f"Nashr qilinganlar: <b>{data.get('published', 0)}</b>\n\n"
        "<b>Bosqichlar</b>\n"
        + ("\n".join(stage_lines) if stage_lines else "Hali ma’lumot yo‘q.")
    )


def build_lead_router(
    cfg: Config,
    db: Database,
    send_user_message: SendUserFunc,
    resolve_username: ResolveUsernameFunc,
) -> Router:
    router = Router(name="lead_crm")

    async def reject_non_admin(message: Message) -> bool:
        if is_admin(cfg, message.from_user.id if message.from_user else None):
            return False
        await message.answer("⛔ Ruxsat yo‘q.")
        return True

    async def show_profile(message: Message, customer: dict[str, Any]) -> None:
        await message.answer(
            lead_profile_text(customer, cfg),
            parse_mode="HTML",
            reply_markup=lead_profile_keyboard(customer["id"]),
        )

    @router.message(Command("cancel"))
    async def cancel_lead_action(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.clear()
        await message.answer("❌ Joriy CRM amali bekor qilindi.")

    @router.message(F.text == "🆕 Lead qo‘shish")
    async def add_lead_start(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        await state.clear()
        await state.set_state(AddLeadStates.waiting_username)
        await message.answer(
            "Yangi leadning Telegram username’ini kiriting.\n"
            "Masalan: <code>@gulnoza_01</code>",
            parse_mode="HTML",
        )

    @router.message(AddLeadStates.waiting_username)
    async def add_lead_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        usernames, invalid = normalize_usernames(message.text or "")
        if invalid or len(usernames) != 1:
            await message.answer("❌ Bitta to‘g‘ri Telegram username kiriting.")
            return
        username = usernames[0]
        await message.answer("🔎 Telegram akkaunt tekshirilyapti…")
        try:
            resolved = await resolve_username(username)
            customer = await db_call(
                db.upsert_customer,
                resolved["telegram_user_id"],
                resolved.get("full_name"),
                resolved.get("username") or username,
            )
            customer = await db_call(
                db.mark_as_lead,
                customer["telegram_user_id"],
                "manual",
            )
        except Exception as exc:
            await message.answer(
                f"❌ Lead qo‘shilmadi: {html.escape(str(exc))}",
                parse_mode="HTML",
            )
            return
        await state.clear()
        await message.answer("✅ Lead CRM’ga qo‘shildi.")
        await show_profile(message, customer)

    @router.message(F.text == "📥 Leadlar")
    async def list_leads(message: Message) -> None:
        if await reject_non_admin(message):
            return
        rows = await db_call(db.list_leads, 20)
        if not rows:
            await message.answer("Hali lead yo‘q. `🆕 Lead qo‘shish` orqali boshlang.")
            return
        await message.answer(
            f"📥 <b>Oxirgi leadlar: {len(rows)}</b>\nLead profilini ochish uchun tanlang.",
            parse_mode="HTML",
            reply_markup=lead_list_keyboard(rows),
        )

    @router.message(F.text == "⚡ Kechikkanlar")
    async def overdue_leads(message: Message) -> None:
        if await reject_non_admin(message):
            return
        rows = await db_call(db.overdue_leads, 20)
        if not rows:
            await message.answer("✅ Hozir kechikkan lead amali yo‘q.")
            return
        await message.answer(
            f"⚡ <b>Kechikkan leadlar: {len(rows)}</b>",
            parse_mode="HTML",
            reply_markup=lead_list_keyboard(rows),
        )

    @router.message(F.text == "📈 CRM Dashboard")
    async def dashboard(message: Message) -> None:
        if await reject_non_admin(message):
            return
        data = await db_call(db.get_lead_dashboard, cfg.timezone)
        await message.answer(dashboard_text(data), parse_mode="HTML")

    @router.callback_query(F.data.startswith("lp:"))
    async def open_profile(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        customer = await db_call(db.get_customer_by_id, customer_id)
        if not customer or not callback.message:
            return
        await show_profile(callback.message, customer)

    @router.callback_query(F.data.startswith("lw:"))
    async def send_welcome_with_followups(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback, "Yuborilyapti…")
        customer_id = (callback.data or "").split(":", 1)[1]
        customer = await db_call(db.get_customer_by_id, customer_id)
        if not customer or not callback.message:
            return
        if customer.get("status") == "do_not_contact":
            await callback.message.answer("🚫 Bu leadga boshqa yozmaslik belgilangan.")
            return
        if not customer.get("username"):
            await callback.message.answer("❌ Avtomatik follow-up uchun username kerak.")
            return
        try:
            text = render_template("welcome", customer, cfg)
            await send_user_message(int(customer["telegram_user_id"]), text)
            plan = build_followup_plan(customer, cfg)
            await db_call(db.create_followup_sequence, customer, plan, cfg.timezone)
            customer = await db_call(
                db.update_lead_fields,
                customer_id,
                pipeline_status="contacted",
            )
        except Exception as exc:
            await callback.message.answer(
                f"❌ Xabar yuborilmadi: {html.escape(str(exc))}",
                parse_mode="HTML",
            )
            return
        await callback.message.answer(
            "✅ Birinchi xabar yuborildi. Javob bo‘lmasa 2, 24 va 72 soatlik "
            "follow-up’lar ishlaydi; lead javob bersa ular avtomatik bekor qilinadi."
        )
        await show_profile(callback.message, customer)

    @router.callback_query(F.data.startswith("lq:"))
    async def quick_replies(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        customer = await db_call(db.get_customer_by_id, customer_id)
        if not customer or not callback.message:
            return
        await callback.message.answer(
            "💬 Shaxsiy akkauntingizdan yuboriladigan professional javobni tanlang:",
            reply_markup=quick_replies_keyboard(customer, cfg),
        )

    @router.callback_query(F.data.startswith("lr:"))
    async def send_quick_reply(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback, "Yuborilyapti…")
        _, customer_id, template_key = (callback.data or "").split(":", 2)
        customer = await db_call(db.get_customer_by_id, customer_id)
        if not customer or not callback.message:
            return
        if customer.get("status") == "do_not_contact":
            await callback.message.answer("🚫 Bu leadga boshqa yozmaslik belgilangan.")
            return
        try:
            text = render_template(template_key, customer, cfg)
            await send_user_message(int(customer["telegram_user_id"]), text)
            transitions = {
                "welcome": {"pipeline_status": "contacted"},
                "questionnaire": {"pipeline_status": "questionnaire"},
                "photo_instagram": {"pipeline_status": "awaiting_documents"},
                "payment_request": {
                    "pipeline_status": "awaiting_payment",
                    "payment_status": "awaiting",
                },
                "payment_confirmed": {
                    "pipeline_status": "paid",
                    "payment_status": "paid",
                    "payment_amount": cfg.service_price_uzs,
                },
                "drafting": {"pipeline_status": "drafting"},
                "published": {
                    "pipeline_status": "published",
                    "published_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            if template_key in transitions:
                customer = await db_call(
                    db.update_lead_fields,
                    customer_id,
                    **transitions[template_key],
                )
            if customer.get("pipeline_status") in {
                "paid",
                "drafting",
                "review",
                "published",
                "lost",
            }:
                await db_call(
                    db.cancel_customer_followups,
                    customer_id,
                    "CRM bosqichi o‘zgargani uchun bekor qilindi",
                )
        except Exception as exc:
            await callback.message.answer(
                f"❌ Xabar yuborilmadi: {html.escape(str(exc))}",
                parse_mode="HTML",
            )
            return
        await callback.message.answer(f"✅ Yuborildi: {TEMPLATE_LABELS[template_key]}")

    @router.callback_query(F.data.startswith("lst:"))
    async def choose_stage(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        if callback.message:
            await callback.message.answer(
                "📌 Yangi CRM bosqichini tanlang:",
                reply_markup=stage_keyboard(customer_id),
            )

    @router.callback_query(F.data.startswith("ls:"))
    async def update_stage(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        _, customer_id, stage = (callback.data or "").split(":", 2)
        if stage not in PIPELINE_LABELS or not callback.message:
            return
        fields: dict[str, Any] = {"pipeline_status": stage}
        if stage == "awaiting_payment":
            fields["payment_status"] = "awaiting"
        elif stage == "paid":
            fields.update(
                payment_status="paid",
                payment_amount=cfg.service_price_uzs,
            )
        elif stage == "published":
            fields["published_at"] = datetime.now(timezone.utc).isoformat()
        customer = await db_call(db.update_lead_fields, customer_id, **fields)
        if stage in {"paid", "drafting", "review", "published", "lost"}:
            await db_call(
                db.cancel_customer_followups,
                customer_id,
                "CRM bosqichi o‘zgargani uchun bekor qilindi",
            )
        await callback.message.answer(f"✅ Bosqich: {PIPELINE_LABELS[stage]}")
        await show_profile(callback.message, customer)

    @router.callback_query(F.data.startswith("lcl:"))
    async def show_checklist(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        customer = await db_call(db.get_customer_by_id, customer_id)
        if customer and callback.message:
            await callback.message.answer(
                "✅ Qabul qilingan ma’lumotlarni belgilang:",
                reply_markup=checklist_keyboard(customer),
            )

    @router.callback_query(F.data.startswith("lct:"))
    async def toggle_checklist(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        _, customer_id, short = (callback.data or "").split(":", 2)
        field = CHECKLIST_CALLBACKS.get(short)
        customer = await db_call(db.get_customer_by_id, customer_id)
        if not field or not customer or not callback.message:
            return
        customer = await db_call(
            db.update_lead_fields,
            customer_id,
            **{field: not bool(customer.get(field))},
        )
        await callback.message.answer(
            "✅ Checklist yangilandi.",
            reply_markup=checklist_keyboard(customer),
        )

    @router.callback_query(F.data.startswith("li:"))
    async def instagram_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        await state.set_state(LeadInstagramStates.waiting_username)
        await state.update_data(lead_customer_id=customer_id)
        if callback.message:
            await callback.message.answer("Instagram username’ini kiriting.")

    @router.message(LeadInstagramStates.waiting_username)
    async def instagram_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        username = (message.text or "").strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username):
            await message.answer("❌ Instagram username noto‘g‘ri.")
            return
        data = await state.get_data()
        customer = await db_call(
            db.update_lead_fields,
            data["lead_customer_id"],
            instagram_username=username,
        )
        await state.clear()
        await message.answer("✅ Instagram saqlandi.")
        await show_profile(message, customer)

    @router.callback_query(F.data.startswith("ln:"))
    async def note_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        await state.set_state(LeadNoteStates.waiting_note)
        await state.update_data(lead_customer_id=customer_id)
        if callback.message:
            await callback.message.answer("Lead uchun ichki izoh yozing.")

    @router.message(LeadNoteStates.waiting_note)
    async def note_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        note = (message.text or "").strip()
        if not note:
            await message.answer("❌ Izoh bo‘sh bo‘lmasin.")
            return
        data = await state.get_data()
        customer = await db_call(
            db.update_lead_fields,
            data["lead_customer_id"],
            notes=note[:2000],
        )
        await state.clear()
        await message.answer("✅ Izoh saqlandi.")
        await show_profile(message, customer)

    @router.callback_query(F.data.startswith("lpub:"))
    async def published_url_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        await state.set_state(LeadPublishedStates.waiting_url)
        await state.update_data(lead_customer_id=customer_id)
        if callback.message:
            await callback.message.answer("Nashr qilingan maqolaning to‘liq HTTPS havolasini kiriting.")

    @router.message(LeadPublishedStates.waiting_url)
    async def published_url_received(message: Message, state: FSMContext) -> None:
        if await reject_non_admin(message):
            return
        url = (message.text or "").strip()
        if not url.startswith("https://") or len(url) > 500:
            await message.answer("❌ To‘g‘ri HTTPS havola kiriting.")
            return
        data = await state.get_data()
        customer = await db_call(
            db.update_lead_fields,
            data["lead_customer_id"],
            published_url=url,
            published_at=datetime.now(timezone.utc).isoformat(),
            pipeline_status="published",
        )
        await db_call(
            db.cancel_customer_followups,
            customer["id"],
            "Maqola nashr qilingani uchun bekor qilindi",
        )
        await state.clear()
        await message.answer("✅ Nashr havolasi saqlandi. Endi tayyor javob orqali yuborishingiz mumkin.")
        await show_profile(message, customer)

    @router.callback_query(F.data.startswith("ldnc:"))
    async def do_not_contact(callback: CallbackQuery) -> None:
        if not is_admin(cfg, callback.from_user.id):
            await safe_callback_answer(callback, "Ruxsat yo‘q", True)
            return
        await safe_callback_answer(callback)
        customer_id = (callback.data or "").split(":", 1)[1]
        customer = await db_call(
            db.update_lead_fields,
            customer_id,
            status="do_not_contact",
            pipeline_status="lost",
            next_action_at=None,
        )
        await db_call(
            db.cancel_customer_followups,
            customer_id,
            "Admin boshqa yozmaslikni belgiladi",
        )
        if callback.message:
            await callback.message.answer("🚫 Leadga boshqa avtomatik xabar yuborilmaydi.")
            await show_profile(callback.message, customer)

    return router
