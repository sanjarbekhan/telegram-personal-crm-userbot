from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    phone_number: str
    telethon_session: str | None

    admin_bot_token: str
    admin_telegram_id: int

    supabase_url: str
    supabase_service_role_key: str

    daily_send_limit: int = 100
    min_delay_seconds: int = 20
    max_delay_seconds: int = 40
    scan_days: int = 30
    run_initial_scan: bool = False
    poll_seconds: int = 8
    schedule_poll_seconds: int = 5
    timezone: str = "Asia/Tashkent"
    service_price_uzs: int = 39000
    sample_article_url: str = "https://bunyodkor.com"
    public_offer_url: str = "https://bunyodkor.com/ommaviy_ofertasi"
    application_form_url: str = ""
    payment_details: str = ""
    daily_report_hour: int = 21
    follow_up_first_hours: int = 2
    follow_up_second_hours: int = 24
    follow_up_final_hours: int = 72

    @staticmethod
    def load() -> "Config":
        load_dotenv()

        def required(name: str) -> str:
            value = os.getenv(name)
            if not value:
                raise RuntimeError(f"Missing required environment variable: {name}")
            return value

        return Config(
            api_id=int(required("API_ID")),
            api_hash=required("API_HASH"),
            phone_number=required("PHONE_NUMBER"),
            telethon_session=os.getenv("TELETHON_SESSION") or None,
            admin_bot_token=required("ADMIN_BOT_TOKEN"),
            admin_telegram_id=int(required("ADMIN_TELEGRAM_ID")),
            supabase_url=required("SUPABASE_URL"),
            supabase_service_role_key=required("SUPABASE_SERVICE_ROLE_KEY"),
            daily_send_limit=int(os.getenv("DAILY_SEND_LIMIT", "100")),
            min_delay_seconds=int(os.getenv("MIN_DELAY_SECONDS", "20")),
            max_delay_seconds=int(os.getenv("MAX_DELAY_SECONDS", "40")),
            scan_days=int(os.getenv("SCAN_DAYS", "30")),
            run_initial_scan=os.getenv("RUN_INITIAL_SCAN", "false").lower() == "true",
            poll_seconds=int(os.getenv("POLL_SECONDS", "8")),
            schedule_poll_seconds=int(os.getenv("SCHEDULE_POLL_SECONDS", "5")),
            timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
            service_price_uzs=int(os.getenv("SERVICE_PRICE_UZS", "39000")),
            sample_article_url=os.getenv(
                "SAMPLE_ARTICLE_URL",
                "https://bunyodkor.com",
            ),
            public_offer_url=os.getenv(
                "PUBLIC_OFFER_URL",
                "https://bunyodkor.com/ommaviy_ofertasi",
            ),
            application_form_url=os.getenv("APPLICATION_FORM_URL", ""),
            payment_details=os.getenv("PAYMENT_DETAILS", ""),
            daily_report_hour=max(
                0,
                min(int(os.getenv("DAILY_REPORT_HOUR", "21")), 23),
            ),
            follow_up_first_hours=max(
                1,
                int(os.getenv("FOLLOW_UP_FIRST_HOURS", "2")),
            ),
            follow_up_second_hours=max(
                1,
                int(os.getenv("FOLLOW_UP_SECOND_HOURS", "24")),
            ),
            follow_up_final_hours=max(
                1,
                int(os.getenv("FOLLOW_UP_FINAL_HOURS", "72")),
            ),
        )
