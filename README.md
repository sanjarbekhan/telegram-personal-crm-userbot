# Telegram Personal CRM Userbot

“O‘zbekiston Bunyodkor yoshlari ensiklopediyasi” leadlarini shaxsiy Telegram akkaunti orqali professional boshqaradigan admin CRM bot.

## Imkoniyatlar

- Telethon orqali shaxsiy Telegram akkauntiga ulanadi.
- Private chatlar va mijozlarni Supabase PostgreSQL bazasiga saqlaydi.
- Tanlangan kundagi mijozlarga navbat bilan follow-up yuboradi.
- Barcha shaxsiy Telegram suhbatlaridan faqat kontakt metadata’sini import qilib, tasdiqdan keyin umumiy broadcast yuboradi.
- Bir yoki bir nechta `@username` uchun aniq sana-vaqtga xabar rejalaydi.
- Rejadagi xabarni oldindan ko‘rsatadi, tasdiqlatadi, statuslarni ko‘rsatadi va yuborilishidan oldin bekor qiladi.
- Har bir username bo‘yicha `sent`, `failed` yoki `skipped` natijasini saqlaydi.
- FloodWait, xavfsiz yuborish oralig‘i va umumiy kunlik limitni hisobga oladi.
- Admin tugmalariga darhol javob beradi; eskirgan callback xatosi worker’ni to‘xtatmaydi.
- Faqat `ADMIN_TELEGRAM_ID` egasi admin paneldan foydalana oladi.
- Username orqali lead qo‘shadi va har biri uchun alohida CRM karta yaratadi.
- Lead bosqichi, to‘lov, anketa, foto, Instagram, hujjatlar va rozilik checklistini saqlaydi.
- Professional tayyor javoblarni shaxsiy akkauntdan bir bosishda yuboradi.
- Birinchi xabardan keyin 2, 24 va 72 soatlik shartli follow-up yaratadi.
- Lead javob bersa yoki CRM bosqichi o‘zgarsa, qolgan follow-up’larni avtomatik bekor qiladi.
- Har kuni Toshkent vaqti bilan belgilangan soatda CRM hisobotini adminga yuboradi.

## Texnologiyalar

- Python 3.11+
- Telethon
- aiogram 3
- Supabase PostgreSQL
- Railway yoki Render Background Worker

## 1. Supabase

Yangi Supabase loyihasining SQL Editor bo‘limida `sql/schema.sql` faylini bir marta ishga tushiring.

Yaratiladigan jadvallar:

- `telegram_customers`
- `telegram_chat_messages`
- `telegram_broadcasts`
- `telegram_broadcast_logs`
- `telegram_scheduled_messages`
- `telegram_scheduled_recipients`
- `crm_settings`

Schema barcha jadvallarda RLS’ni yoqadi, `anon` va `authenticated` rollaridan huquqlarni olib tashlaydi. Bot serverda faqat `service_role` kalitidan foydalanadi.

## 2. Telegram sozlamalari

1. `https://my.telegram.org/apps` orqali shaxsiy akkaunt uchun `API_ID` va `API_HASH` oling.
2. `@BotFather` orqali alohida admin bot yarating va tokenini oling.
3. O‘zingizning Telegram ID’ingizni `ADMIN_TELEGRAM_ID` sifatida yozing.
4. Lokal kompyuterda `python -m app.make_session` bilan yangi akkauntning `TELETHON_SESSION` qiymatini yarating.

`TELETHON_SESSION`, bot tokeni, Supabase `service_role` kaliti, `.env` va `*.session` fayllarini GitHub’ga yuklamang.

## 3. Lokal ishga tushirish

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.make_session
python -m app.main
```

Windows uchun virtual muhitni faollashtirish:

```powershell
.venv\Scripts\activate
```

## 4. Professional lead oqimi

Admin botda:

1. `🆕 Lead qo‘shish` orqali ariza qoldirgan odamning username’ini kiriting.
2. Lead kartasidan `⚡ Birinchi xabar + 3 follow-up` tugmasini bosing.
3. Birinchi professional xabar darhol shaxsiy akkauntingizdan yuboriladi.
4. Javob bo‘lmasa 2, 24 va 72 soatdan keyingi muloyim eslatmalar ishlaydi.
5. Lead javob bersa, eslatmalar bekor qilinadi va admin botga xabar keladi.
6. `📌 Bosqich`, `✅ Checklist`, `📝 Izoh` va `🔗 Nashr havolasi` orqali jarayonni boshqaring.

Bosqichlar: `new`, `contacted`, `interested`, `questionnaire`, `awaiting_documents`, `awaiting_payment`, `paid`, `drafting`, `review`, `published`, `lost`.

`💬 Tayyor javoblar` ichida birinchi xabar, qisqa afzalliklar, anketa, foto/Instagram, to‘lov, maqola tayyorlanishi va nashr xabarlari mavjud. `APPLICATION_FORM_URL` yoki `PAYMENT_DETAILS` sozlanmagan bo‘lsa, tegishli tugma xavfsizlik uchun ko‘rsatilmaydi. Production uchun `APPLICATION_FORM_URL=https://www.bunyodkor.com/anketa` qiymatini ishlating; bot havolaga leadning Telegram username’ini avtomatik qo‘shadi.

`📈 CRM Dashboard` jami leadlar, bugungi leadlar, kechikkan amallar, to‘lovlar va nashrlar sonini ko‘rsatadi. Shu hisobot `DAILY_REPORT_HOUR` vaqtida har kuni avtomatik yuboriladi.

## 5. Rejadagi xabar

Admin botda:

1. `⏰ Xabar rejalash` tugmasini bosing.
2. Username’larni vergul yoki yangi qatorda kiriting: `@ali_01, @vali_02`.
3. `Asia/Tashkent` bo‘yicha vaqtni kiriting: `2026-08-20 14:30` yoki `2026-08-20 14:30:15`.
4. Xabar matnini yozing.
5. Preview’ni tekshirib, tasdiqlang.

Belgilangan vaqt kelganda worker xabarlarni shaxsiy akkaunt nomidan yuborishni boshlaydi. Bitta username bo‘lsa xabar darhol yuboriladi; bir nechta username bo‘lsa Telegram xavfsizligi uchun ular orasida sozlangan interval saqlanadi.

`🗓 Rejadagi xabarlar` tugmasi orqali oxirgi ishlarni ko‘rish va hali boshlanmagan xabarni bekor qilish mumkin.

## 6. CRM broadcast

- `/scan 30` — oxirgi 30 kunlik private chatlarni bazaga tushiradi.
- `📅 Sana bo‘yicha mijozlar` — tanlangan kundagi mijozlarni ko‘rsatadi.
- `📨 Broadcast yuborish` — shu mijozlarga follow-up navbatini yaratadi.
- `👥 Barchaga broadcast` — barcha shaxsiy suhbatlardagi inson kontaktlarini yuklaydi va umumiy navbat yaratadi. Eski xabarlarning matni import qilinmaydi.
- `/status 123456789 do_not_contact` — mijozga boshqa yozilmasligini belgilaydi.
- `/report` — oxirgi broadcast natijalarini ko‘rsatadi.

Umumiy broadcast botlar, guruhlar, o‘chirilgan akkauntlar, o‘z akkauntingiz va `do_not_contact` statusidagi kontaktlarni avtomatik o‘tkazib yuboradi. Jo‘natishdan oldin kontaktlar soni, taxminiy vaqt va to‘liq xabar preview’i ko‘rsatiladi. Katta navbat kunlik limitga yetganda to‘xtab, keyingi kuni avtomatik davom etadi.

## 7. Deploy

Background Worker uchun:

```text
Build: pip install -r requirements.txt
Start: python -m app.main
```

Kerakli Environment Variables `.env.example` ichida berilgan. Server doim ishlab turishi kerak; aks holda rejadagi xabar server qayta yoqilgandan keyingina yuboriladi.

## Mas’uliyatli foydalanish

- Faqat sizdan xabar kutayotgan yoki aloqa qilishga rozilik bergan odamlarga yozing.
- Telegram cheklovlarini aylanib o‘tishga urinmang va yuborish oralig‘ini keskin kamaytirmang.
- Keraksiz kontaktlarni `do_not_contact` bilan bloklang.
- `DAILY_SEND_LIMIT` va FloodWait himoyasini yoqilgan holda qoldiring.

## Fayl tuzilmasi

```text
app/
  admin_bot.py
  config.py
  db.py
  dashboard.py
  lead_crm.py
  lead_templates.py
  main.py
  make_session.py
  scheduling.py
  sender_worker.py
  userbot.py
sql/
  schema.sql
.env.example
requirements.txt
README.md
```
