from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if TYPE_CHECKING:
    from app.config import Config


PIPELINE_LABELS = {
    "new": "🆕 Yangi",
    "contacted": "📨 Aloqa qilindi",
    "interested": "🔥 Qiziqdi",
    "questionnaire": "📋 Anketa jarayonida",
    "awaiting_documents": "🗂 Hujjatlar kutilmoqda",
    "awaiting_payment": "💳 To‘lov kutilmoqda",
    "paid": "✅ To‘landi",
    "drafting": "✍️ Maqola tayyorlanmoqda",
    "review": "🔎 Tasdiqlashda",
    "published": "🌐 Nashr qilindi",
    "lost": "⚪ Yopildi",
}

TERMINAL_PIPELINE_STATUSES = {"paid", "drafting", "review", "published", "lost"}

CHECKLIST_FIELDS = {
    "application_complete": "Anketa",
    "photo_received": "Asosiy rasm",
    "documents_received": "Tasdiqlovchi hujjatlar",
    "consent_received": "Nashrga rozilik",
}

TEMPLATE_LABELS = {
    "welcome": "👋 Birinchi xabar",
    "benefits": "ℹ️ Qisqa afzalliklar",
    "questionnaire": "📋 Anketa havolasi",
    "photo_instagram": "🖼 Foto va Instagram",
    "payment_request": "💳 To‘lov ma’lumoti",
    "payment_confirmed": "✅ To‘lov tasdiqlandi",
    "drafting": "✍️ Maqola tayyorlanmoqda",
    "published": "🌐 Maqola nashr qilindi",
}

TEMPLATES = {
    "welcome": (
        "Assalomu alaykum, {first_name}!\n\n"
        "Siz “O‘zbekiston Bunyodkor yoshlari ensiklopediyasi”ga kirish uchun "
        "ariza qoldirgandingiz. Arizangiz qabul qilindi.\n\n"
        "Ensiklopediyada siz haqingizda professional biografik maqola tayyorlanadi "
        "va bunyodkor.com saytida shaxsiy havola bilan e’lon qilinadi. Havolani "
        "rezyume, portfolio va ijtimoiy tarmoqlaringizda ishlatishingiz mumkin.\n\n"
        "Hozirgi xizmat narxi: {price}. Maqola to‘liq ma’lumot va to‘lov "
        "olingandan keyin odatda 24 soat ichida tayyorlanadi.\n\n"
        "Namuna: {sample_url}\n"
        "Ommaviy oferta: {offer_url}\n\n"
        "Boshlaymizmi?\n"
        "1. Ha, boshlaymiz\n"
        "2. Savolim bor\n"
        "3. Keyinroq"
    ),
    "benefits": (
        "Ensiklopediyaga kirishning asosiy afzalliklari:\n\n"
        "• Siz haqingizda professional biografik sahifa yaratiladi.\n"
        "• Shaxsiy havolani rezyume, portfolio va ijtimoiy tarmoqlarda ishlatishingiz mumkin.\n"
        "• Sahifa qidiruv tizimlari tomonidan indekslanishi va ism-familiyangiz "
        "bo‘yicha topilish imkoniyatini oshirishi mumkin.\n"
        "• Muhim yutuq va loyihalaringiz bitta ishonchli sahifada jamlanadi.\n"
        "• Nashrdan keyin 7 kun davomida bepul tahrirlash imkoniyati beriladi.\n\n"
        "Namuna: {sample_url}"
    ),
    "questionnaire": (
        "Biografik maqola uchun anketani quyidagi havola orqali to‘ldiring:\n"
        "{form_url}\n\n"
        "Anketada ma’lumotlarni saqlab, keyin davom ettirishingiz mumkin. "
        "Yakunida yuborishdan oldin barcha javoblarni tekshiring."
    ),
    "photo_instagram": (
        "Maqolani tayyorlash uchun quyidagilarni ham yuboring:\n\n"
        "1. To‘g‘riga qarab tushgan, sifatli asosiy rasm.\n"
        "2. Instagram username’ingiz.\n"
        "3. Asosiy yutuqlarni tasdiqlovchi sertifikat yoki hujjatlar.\n"
        "4. Ushbu ma’lumot va rasmlarni maqolada e’lon qilishga roziligingiz."
    ),
    "payment_request": (
        "Maqola tayyorlash ishlarini boshlash uchun to‘lov ma’lumoti:\n\n"
        "{payment_details}\n\n"
        "To‘lov miqdori: {price}. To‘lovdan keyin chekni shu chatga yuboring."
    ),
    "payment_confirmed": (
        "To‘lovingiz qabul qilindi, rahmat! ✅\n\n"
        "Maqolangiz tayyorlash navbatiga qo‘shildi. To‘liq ma’lumotlar qabul "
        "qilinganidan keyin odatda 24 soat ichida natijani yuboramiz."
    ),
    "drafting": (
        "Ma’lumotlaringiz to‘liq qabul qilindi. ✅\n\n"
        "Hozir biografik maqolangiz tahririyat tomonidan tayyorlanmoqda. "
        "Tayyor bo‘lgach, tekshirishingiz uchun havolani yuboramiz."
    ),
    "published": (
        "Maqolangiz nashr qilindi! 🎉\n\n"
        "Havola: {published_url}\n\n"
        "Iltimos, ism, ta’lim va yutuqlaringizni tekshirib chiqing. Nashrdan "
        "keyingi 7 kun ichida aniqlangan tahrirlarni bepul kiritamiz."
    ),
    "followup_2h": (
        "Assalomu alaykum, {first_name}. Oldingi xabarimni ko‘rishga "
        "ulgurdingizmi? Savolingiz bo‘lsa, bemalol yozishingiz mumkin."
    ),
    "followup_24h": (
        "Assalomu alaykum, {first_name}. Ensiklopediya maqolasi namunasini "
        "yana bir bor qoldiraman: {sample_url}\n\n"
        "Davom ettirishni istasangiz, “Boshlaymiz” deb yozishingiz kifoya."
    ),
    "followup_72h": (
        "Assalomu alaykum, {first_name}. Hozircha arizangizni kutish "
        "holatida qoldiramiz. Keyinroq davom ettirishni istasangiz, shu chatga "
        "yozishingiz mumkin. Boshqa eslatma yubormaymiz."
    ),
}


def format_price(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " so‘m"


def personalized_form_url(base_url: str, username: str | None) -> str:
    """Add the lead username without discarding existing safe query parameters."""
    clean_url = (base_url or "").strip()
    clean_username = (username or "").strip().lstrip("@")
    if not clean_url or not clean_username:
        return clean_url

    parts = urlsplit(clean_url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "telegram"]
    query.append(("telegram", clean_username))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def template_context(customer: dict[str, Any], cfg: Config) -> dict[str, str]:
    full_name = (customer.get("full_name") or "").strip()
    first_name = full_name.split()[0] if full_name else ""
    return {
        "first_name": first_name,
        "full_name": full_name,
        "price": format_price(cfg.service_price_uzs),
        "sample_url": cfg.sample_article_url,
        "offer_url": cfg.public_offer_url,
        "form_url": personalized_form_url(
            cfg.application_form_url,
            customer.get("username"),
        ),
        "payment_details": cfg.payment_details,
        "published_url": customer.get("published_url") or "",
    }


def render_template(key: str, customer: dict[str, Any], cfg: Config) -> str:
    if key not in TEMPLATES:
        raise KeyError(f"Unknown lead template: {key}")
    return TEMPLATES[key].format_map(template_context(customer, cfg)).strip()


def available_quick_replies(customer: dict[str, Any], cfg: Config) -> list[str]:
    keys = ["welcome", "benefits", "photo_instagram", "payment_confirmed", "drafting"]
    if cfg.application_form_url:
        keys.insert(2, "questionnaire")
    if cfg.payment_details:
        keys.insert(-2, "payment_request")
    if customer.get("published_url"):
        keys.append("published")
    return keys


def build_followup_plan(
    customer: dict[str, Any],
    cfg: Config,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    start = now or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    steps = [
        (1, cfg.follow_up_first_hours, "followup_2h"),
        (2, cfg.follow_up_second_hours, "followup_24h"),
        (3, cfg.follow_up_final_hours, "followup_72h"),
    ]
    steps.sort(key=lambda item: item[1])
    return [
        {
            "sequence_step": step,
            "template_key": key,
            "scheduled_at": start + timedelta(hours=hours),
            "message_text": render_template(key, customer, cfg),
        }
        for step, hours, key in steps
    ]
