# Telegram Personal CRM Userbot

Bu loyiha shaxsiy Telegram akkauntingiz orqali oldin yozishgan private chat mijozlarga sana bo‘yicha follow-up yuborish uchun tayyorlangan.

## Nima qiladi?

- Shaxsiy Telegram akkauntingizga Telethon orqali ulanadi.
- Private chatlardagi mijozlarni Supabase bazaga saqlaydi.
- Har bir xabarni sana bo‘yicha saqlaydi.
- Admin Telegram bot orqali sana tanlaysiz.
- O‘sha kuni yozishgan mijozlar topiladi.
- Siz bitta xabar yozasiz va tasdiqlaysiz.
- Xabarlar sizning shaxsiy Telegram akkauntingizdan navbat bilan yuboriladi.
- `do_not_contact` statusidagi mijozlarga xabar yuborilmaydi.
- Delay va kunlik limit bor.

## Texnologiyalar

- Python
- Telethon
- aiogram 3
- Supabase PostgreSQL
- Render Background Worker

## 1. Supabase sozlash

Supabase loyihangizni oching va SQL Editor ichida `sql/schema.sql` faylini ishga tushiring.

Yaratiladigan jadvallar:

- `telegram_customers`
- `telegram_chat_messages`
- `telegram_broadcasts`
- `telegram_broadcast_logs`
- `crm_settings`

## 2. Telegram API_ID va API_HASH olish

1. `https://my.telegram.org/apps` ga kiring.
2. Telegram raqamingiz bilan login qiling.
3. App yarating.
4. `api_id` va `api_hash` ni oling.

## 3. Admin bot token olish

1. Telegram’da `@BotFather` ni oching.
2. `/newbot` qiling.
3. Bot tokenni oling.
4. O‘zingizning Telegram ID’ingizni `ADMIN_TELEGRAM_ID` sifatida yozing.

Telegram ID bilish uchun `@userinfobot` kabi botdan foydalanishingiz mumkin.

## 4. Lokal ishga tushirish

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows’da:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`.env` ichini to‘ldiring.

## 5. StringSession yaratish

Render’da Telegram kod/SMS so‘ramasligi uchun sessiyani lokalda yarating:

```bash
python -m app.make_session
```

Telegram kodini kiriting. Chiqqan uzun `TELETHON_SESSION` qiymatini Render Environment Variables ichiga qo‘ying.

Muhim: `TELETHON_SESSION`, `.env`, `*.session` fayllarni hech qachon GitHub’ga yuklamang.

## 6. Lokal test

```bash
python -m app.main
```

Admin botga kiring va `/start` bosing.

## 7. Chatlarni skan qilish

Admin bot ichida:

```text
/scan 30
```

Bu oxirgi 30 kunlik private chatlarni Supabase bazaga tushiradi.

## 8. Broadcast yuborish

Admin botda:

1. `📨 Broadcast yuborish` ni bosing.
2. Sana kiriting: `2026-06-18`
3. Bot o‘sha kuni yozishgan mijozlar sonini ko‘rsatadi.
4. Xabar matnini yozing.
5. Tasdiqlang.
6. Sender worker xabarlarni shaxsiy akkauntingiz orqali yuboradi.

## 9. Status o‘zgartirish

Mijozga boshqa yozmaslik uchun:

```text
/status 123456789 do_not_contact
```

Follow-up status berish uchun:

```text
/status 123456789 follow_up
```

Statuslar:

- `new`
- `contacted`
- `interested`
- `follow_up`
- `paid`
- `rejected`
- `do_not_contact`

## 10. Render deploy

### GitHub

1. Bu papkani GitHub repository’ga yuklang.
2. `.env`, session fayllar va maxfiy tokenlar GitHub’ga chiqmasin.

### Render

Render’da yangi **Background Worker** yarating.

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
python -m app.main
```

Environment Variables:

```env
API_ID=...
API_HASH=...
PHONE_NUMBER=+998...
TELETHON_SESSION=...
ADMIN_BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
DAILY_SEND_LIMIT=100
MIN_DELAY_SECONDS=20
MAX_DELAY_SECONDS=40
SCAN_DAYS=30
RUN_INITIAL_SCAN=false
POLL_SECONDS=8
```

## Muhim xavfsizlik

- Faqat oldin yozishgan mijozlarga yuboring.
- Juda ko‘p odamga birdaniga yubormang.
- Delayni kamaytirmang.
- `do_not_contact` statusidan foydalaning.
- `TELETHON_SESSION` ni hech kimga bermang.
- Supabase `SERVICE_ROLE_KEY` ni faqat server/Render’da saqlang.

## Fayl tuzilmasi

```text
app/
  admin_bot.py
  config.py
  db.py
  main.py
  make_session.py
  sender_worker.py
  userbot.py
sql/
  schema.sql
.env.example
.gitignore
render.yaml
requirements.txt
README.md
```
