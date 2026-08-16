from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from supabase import Client, create_client

from app.config import Config


class Database:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client: Client = create_client(
            cfg.supabase_url,
            cfg.supabase_service_role_key,
        )

    def upsert_customer(
        self,
        telegram_user_id: int,
        full_name: str | None,
        username: str | None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
            "full_name": full_name,
            "username": username,
            "last_seen_at": now,
            "updated_at": now,
        }
        if phone:
            payload["phone"] = phone

        res = (
            self.client.table("telegram_customers")
            .upsert(payload, on_conflict="telegram_user_id")
            .execute()
        )
        if res.data:
            return res.data[0]

        res = (
            self.client.table("telegram_customers")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError("Customer upsert failed")
        return res.data[0]

    def save_chat_message(
        self,
        customer_id: str,
        telegram_user_id: int,
        message_id: int,
        direction: str,
        message_text: str | None,
        message_dt: date,
        created_at: datetime | None = None,
        update_activity: bool = True,
    ) -> None:
        payload = {
            "customer_id": customer_id,
            "telegram_user_id": telegram_user_id,
            "message_id": message_id,
            "direction": direction,
            "message_text": message_text,
            "message_date": message_dt.isoformat(),
            "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
        }
        self.client.table("telegram_chat_messages").upsert(
            payload,
            on_conflict="telegram_user_id,message_id",
        ).execute()

        if update_activity:
            activity_field = (
                "last_outbound_at" if direction == "outgoing" else "last_inbound_at"
            )
            self.client.table("telegram_customers").update(
                {
                    activity_field: payload["created_at"],
                    "last_seen_at": payload["created_at"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("telegram_user_id", telegram_user_id).execute()

    def get_customers_by_date(self, target_date: str) -> list[dict[str, Any]]:
        messages = (
            self.client.table("telegram_chat_messages")
            .select("telegram_user_id")
            .eq("message_date", target_date)
            .execute()
        ).data or []

        user_ids = sorted({row["telegram_user_id"] for row in messages})
        if not user_ids:
            return []

        return (
            self.client.table("telegram_customers")
            .select("*")
            .in_("telegram_user_id", user_ids)
            .neq("status", "do_not_contact")
            .execute()
        ).data or []

    def get_broadcast_customers(
        self,
        telegram_user_ids: list[int],
    ) -> list[dict[str, Any]]:
        """Return eligible customers for the exact private dialogs found by Telethon."""
        unique_user_ids = list(dict.fromkeys(int(value) for value in telegram_user_ids))
        if not unique_user_ids:
            return []

        customers: list[dict[str, Any]] = []
        for start in range(0, len(unique_user_ids), 500):
            rows = (
                self.client.table("telegram_customers")
                .select("*")
                .in_("telegram_user_id", unique_user_ids[start : start + 500])
                .neq("status", "do_not_contact")
                .order("created_at")
                .execute()
            ).data or []
            customers.extend(rows)

        return customers

    def create_broadcast(
        self,
        target_date: str | None,
        message_text: str,
        customers: list[dict[str, Any]],
        *,
        target_scope: str = "date",
    ) -> dict[str, Any]:
        if target_scope not in {"date", "all"}:
            raise ValueError("Unsupported broadcast target scope")
        if target_scope == "date" and not target_date:
            raise ValueError("Date broadcast requires target_date")

        broadcast = (
            self.client.table("telegram_broadcasts")
            .insert(
                {
                    "target_date": target_date,
                    "target_scope": target_scope,
                    "message_text": message_text,
                    "total_count": len(customers),
                    "status": "queued",
                }
            )
            .execute()
        ).data[0]

        logs = [
            {
                "broadcast_id": broadcast["id"],
                "customer_id": customer["id"],
                "telegram_user_id": customer["telegram_user_id"],
                "status": "pending",
            }
            for customer in customers
        ]
        for start in range(0, len(logs), 500):
            self.client.table("telegram_broadcast_logs").upsert(
                logs[start : start + 500],
                on_conflict="broadcast_id,telegram_user_id",
            ).execute()
        return broadcast

    def get_next_pending_log(self) -> dict[str, Any] | None:
        rows = (
            self.client.table("telegram_broadcast_logs")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def get_broadcast(self, broadcast_id: str) -> dict[str, Any] | None:
        rows = (
            self.client.table("telegram_broadcasts")
            .select("*")
            .eq("id", broadcast_id)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any] | None:
        rows = (
            self.client.table("telegram_customers")
            .select("*")
            .eq("id", customer_id)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def get_customer_by_telegram_id(
        self,
        telegram_user_id: int,
    ) -> dict[str, Any] | None:
        rows = (
            self.client.table("telegram_customers")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def mark_as_lead(
        self,
        telegram_user_id: int,
        source: str = "manual",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_customer_by_telegram_id(telegram_user_id)
        payload: dict[str, Any] = {
            "is_lead": True,
            "lead_source": source[:50],
            "updated_at": now,
        }
        if not existing or not existing.get("is_lead"):
            payload.update(
                pipeline_status="new",
                lead_temperature="warm",
            )
        rows = (
            self.client.table("telegram_customers")
            .update(payload)
            .eq("telegram_user_id", telegram_user_id)
            .execute()
        ).data or []
        if not rows:
            raise RuntimeError("Lead topilmadi")
        return rows[0]

    def update_lead_fields(self, customer_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "pipeline_status",
            "lead_temperature",
            "notes",
            "next_action_at",
            "payment_status",
            "payment_amount",
            "application_complete",
            "photo_received",
            "instagram_username",
            "documents_received",
            "consent_received",
            "published_url",
            "published_at",
            "is_lead",
            "lead_source",
            "status",
        }
        payload = {key: value for key, value in fields.items() if key in allowed}
        if not payload:
            raise ValueError("Yangilanadigan lead maydoni yo‘q")
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        rows = (
            self.client.table("telegram_customers")
            .update(payload)
            .eq("id", customer_id)
            .execute()
        ).data or []
        if not rows:
            raise RuntimeError("Lead yangilanmadi")
        return rows[0]

    def list_leads(self, limit: int = 20) -> list[dict[str, Any]]:
        return (
            self.client.table("telegram_customers")
            .select("*")
            .eq("is_lead", True)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        ).data or []

    def overdue_leads(self, limit: int = 20) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        return (
            self.client.table("telegram_customers")
            .select("*")
            .eq("is_lead", True)
            .lte("next_action_at", now)
            .neq("status", "do_not_contact")
            .not_.in_(
                "pipeline_status",
                "(paid,drafting,review,published,lost)",
            )
            .order("next_action_at")
            .limit(limit)
            .execute()
        ).data or []

    def get_lead_dashboard(
        self,
        timezone_name: str = "Asia/Tashkent",
    ) -> dict[str, Any]:
        rows = (
            self.client.table("telegram_customers")
            .select(
                "pipeline_status,payment_status,next_action_at,created_at,status"
            )
            .eq("is_lead", True)
            .execute()
        ).data or []
        now = datetime.now(timezone.utc)
        try:
            local_zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            local_zone = timezone.utc
        today = now.astimezone(local_zone).date()
        stages: dict[str, int] = {}
        overdue = 0
        new_today = 0
        for row in rows:
            pipeline_status = row.get("pipeline_status") or "new"
            stages[pipeline_status] = stages.get(pipeline_status, 0) + 1
            created_at = row.get("created_at")
            if created_at:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created.astimezone(local_zone).date() == today:
                    new_today += 1
            next_action = row.get("next_action_at")
            if next_action and row.get("status") != "do_not_contact":
                due = datetime.fromisoformat(next_action.replace("Z", "+00:00"))
                if due <= now and pipeline_status not in {
                    "paid",
                    "drafting",
                    "review",
                    "published",
                    "lost",
                }:
                    overdue += 1
        return {
            "total": len(rows),
            "new_today": new_today,
            "overdue": overdue,
            "paid": sum(1 for row in rows if row.get("payment_status") == "paid"),
            "published": stages.get("published", 0),
            "stages": stages,
        }

    def update_log(
        self,
        log_id: str,
        status: str,
        error_text: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"status": status}
        if status == "sent":
            payload["sent_at"] = datetime.now(timezone.utc).isoformat()
        if error_text:
            payload["error_text"] = error_text[:1000]
        self.client.table("telegram_broadcast_logs").update(payload).eq(
            "id",
            log_id,
        ).execute()

    def mark_broadcast_running(self, broadcast_id: str) -> None:
        broadcast = self.get_broadcast(broadcast_id)
        payload: dict[str, Any] = {"status": "running"}
        if broadcast and not broadcast.get("started_at"):
            payload["started_at"] = datetime.now(timezone.utc).isoformat()
        self.client.table("telegram_broadcasts").update(payload).eq(
            "id",
            broadcast_id,
        ).execute()

    def recalc_broadcast_counts(self, broadcast_id: str) -> dict[str, int]:
        logs = (
            self.client.table("telegram_broadcast_logs")
            .select("status")
            .eq("broadcast_id", broadcast_id)
            .execute()
        ).data or []
        counts = {
            "sent_count": sum(1 for row in logs if row["status"] == "sent"),
            "failed_count": sum(1 for row in logs if row["status"] == "failed"),
            "skipped_count": sum(1 for row in logs if row["status"] == "skipped"),
        }
        pending = sum(
            1 for row in logs if row["status"] in ("pending", "processing")
        )
        payload: dict[str, Any] = counts.copy()
        if pending == 0:
            payload["status"] = "finished"
            payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.client.table("telegram_broadcasts").update(payload).eq(
            "id",
            broadcast_id,
        ).execute()
        return counts

    def create_scheduled_message(
        self,
        usernames: list[str],
        message_text: str,
        scheduled_at: datetime,
        timezone_name: str,
        *,
        kind: str = "manual",
        customer_id: str | None = None,
        cancel_on_reply: bool = False,
        sequence_step: int | None = None,
        template_key: str | None = None,
        telegram_user_id: int | None = None,
    ) -> dict[str, Any]:
        job_payload: dict[str, Any] = {
            "scheduled_at": scheduled_at.astimezone(timezone.utc).isoformat(),
            "timezone": timezone_name,
            "message_text": message_text,
            "total_count": len(usernames),
            "status": "queued",
            "kind": kind,
            "customer_id": customer_id,
            "cancel_on_reply": cancel_on_reply,
            "sequence_step": sequence_step,
            "template_key": template_key,
        }
        job = (
            self.client.table("telegram_scheduled_messages")
            .insert(job_payload)
            .execute()
        ).data[0]

        recipients = [
            {
                "scheduled_message_id": job["id"],
                "username": username,
                "telegram_user_id": telegram_user_id,
                "status": "pending",
            }
            for username in usernames
        ]
        self.client.table("telegram_scheduled_recipients").upsert(
            recipients,
            on_conflict="scheduled_message_id,username",
        ).execute()
        return job

    def create_followup_sequence(
        self,
        customer: dict[str, Any],
        plan: list[dict[str, Any]],
        timezone_name: str,
    ) -> list[dict[str, Any]]:
        username = (customer.get("username") or "").strip().lstrip("@").lower()
        if not username:
            raise ValueError("Follow-up uchun lead username'i kerak")

        self.cancel_customer_followups(
            customer["id"],
            reason="Yangi follow-up ketma-ketligi yaratildi",
        )
        jobs = []
        for item in plan:
            jobs.append(
                self.create_scheduled_message(
                    usernames=[username],
                    message_text=item["message_text"],
                    scheduled_at=item["scheduled_at"],
                    timezone_name=timezone_name,
                    kind="follow_up",
                    customer_id=customer["id"],
                    cancel_on_reply=True,
                    sequence_step=item["sequence_step"],
                    template_key=item["template_key"],
                    telegram_user_id=customer["telegram_user_id"],
                )
            )
        first_at = min(item["scheduled_at"] for item in plan)
        self.update_lead_fields(customer["id"], next_action_at=first_at.isoformat())
        return jobs

    def get_due_scheduled_message(self) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        rows = (
            self.client.table("telegram_scheduled_messages")
            .select("*")
            .in_("status", ["queued", "running"])
            .lte("scheduled_at", now)
            .order("scheduled_at")
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def get_next_scheduled_recipient(
        self,
        scheduled_message_id: str,
    ) -> dict[str, Any] | None:
        rows = (
            self.client.table("telegram_scheduled_recipients")
            .select("*")
            .eq("scheduled_message_id", scheduled_message_id)
            .eq("status", "pending")
            .order("created_at")
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def mark_scheduled_message_running(self, scheduled_message_id: str) -> None:
        job = self.get_scheduled_message(scheduled_message_id)
        payload: dict[str, Any] = {"status": "running"}
        if job and not job.get("started_at"):
            payload["started_at"] = datetime.now(timezone.utc).isoformat()
        self.client.table("telegram_scheduled_messages").update(payload).eq(
            "id",
            scheduled_message_id,
        ).execute()

    def get_scheduled_message(
        self,
        scheduled_message_id: str,
    ) -> dict[str, Any] | None:
        rows = (
            self.client.table("telegram_scheduled_messages")
            .select("*")
            .eq("id", scheduled_message_id)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def update_scheduled_recipient(
        self,
        recipient_id: str,
        status: str,
        telegram_user_id: int | None = None,
        error_text: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"status": status}
        if telegram_user_id is not None:
            payload["telegram_user_id"] = telegram_user_id
        if status == "sent":
            payload["sent_at"] = datetime.now(timezone.utc).isoformat()
        if error_text:
            payload["error_text"] = error_text[:1000]
        self.client.table("telegram_scheduled_recipients").update(payload).eq(
            "id",
            recipient_id,
        ).execute()

    def recalc_scheduled_counts(
        self,
        scheduled_message_id: str,
    ) -> dict[str, int]:
        recipients = (
            self.client.table("telegram_scheduled_recipients")
            .select("status")
            .eq("scheduled_message_id", scheduled_message_id)
            .execute()
        ).data or []
        counts = {
            "sent_count": sum(1 for row in recipients if row["status"] == "sent"),
            "failed_count": sum(
                1 for row in recipients if row["status"] == "failed"
            ),
            "skipped_count": sum(
                1 for row in recipients if row["status"] == "skipped"
            ),
        }
        pending = sum(
            1
            for row in recipients
            if row["status"] in ("pending", "processing")
        )
        payload: dict[str, Any] = counts.copy()
        if pending == 0:
            payload["status"] = "finished"
            payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.client.table("telegram_scheduled_messages").update(payload).eq(
            "id",
            scheduled_message_id,
        ).execute()
        return counts

    def recent_scheduled_messages(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return (
            self.client.table("telegram_scheduled_messages")
            .select("*")
            .order("scheduled_at", desc=True)
            .limit(limit)
            .execute()
        ).data or []

    def cancel_scheduled_message(self, scheduled_message_id: str) -> bool:
        rows = (
            self.client.table("telegram_scheduled_messages")
            .update(
                {
                    "status": "cancelled",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", scheduled_message_id)
            .eq("status", "queued")
            .execute()
        ).data or []
        if not rows:
            return False
        self.client.table("telegram_scheduled_recipients").update(
            {"status": "skipped", "error_text": "Admin tomonidan bekor qilindi"}
        ).eq("scheduled_message_id", scheduled_message_id).eq(
            "status",
            "pending",
        ).execute()
        return True

    def mark_scheduled_message_cancelled(
        self,
        scheduled_message_id: str,
        reason: str,
    ) -> None:
        self.client.table("telegram_scheduled_messages").update(
            {
                "status": "cancelled",
                "cancelled_reason": reason[:500],
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", scheduled_message_id).in_(
            "status",
            ["queued", "running"],
        ).execute()
        self.client.table("telegram_scheduled_recipients").update(
            {"status": "skipped", "error_text": reason[:1000]}
        ).eq("scheduled_message_id", scheduled_message_id).in_(
            "status",
            ["pending", "processing"],
        ).execute()

    def cancel_customer_followups(
        self,
        customer_id: str,
        reason: str = "Lead javob berdi",
    ) -> int:
        jobs = (
            self.client.table("telegram_scheduled_messages")
            .select("id")
            .eq("customer_id", customer_id)
            .eq("kind", "follow_up")
            .in_("status", ["queued", "running"])
            .execute()
        ).data or []
        for job in jobs:
            self.mark_scheduled_message_cancelled(job["id"], reason)
        self.update_lead_fields(customer_id, next_action_at=None)
        return len(jobs)

    def handle_incoming_lead_reply(
        self,
        telegram_user_id: int,
    ) -> tuple[dict[str, Any] | None, int]:
        customer = self.get_customer_by_telegram_id(telegram_user_id)
        if not customer or not customer.get("is_lead"):
            return customer, 0

        fields: dict[str, Any] = {"next_action_at": None}
        if customer.get("pipeline_status") in ("new", "contacted"):
            fields["pipeline_status"] = "interested"
        self.update_lead_fields(customer["id"], **fields)
        cancelled = self.cancel_customer_followups(
            customer["id"],
            reason="Lead javob bergani uchun avtomatik bekor qilindi",
        )
        return self.get_customer_by_id(customer["id"]), cancelled

    def should_cancel_followup(self, job: dict[str, Any]) -> bool:
        if job.get("kind") != "follow_up" or not job.get("cancel_on_reply"):
            return False
        customer_id = job.get("customer_id")
        if not customer_id:
            return True
        customer = self.get_customer_by_id(customer_id)
        if not customer or not customer.get("is_lead"):
            return True
        if customer.get("status") == "do_not_contact":
            return True
        if customer.get("pipeline_status") in {
            "paid",
            "drafting",
            "review",
            "published",
            "lost",
        }:
            return True
        created_at = job.get("created_at")
        last_inbound_at = customer.get("last_inbound_at")
        if created_at and last_inbound_at:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            inbound = datetime.fromisoformat(last_inbound_at.replace("Z", "+00:00"))
            return inbound > created
        return False

    def refresh_customer_next_action(self, customer_id: str) -> None:
        rows = (
            self.client.table("telegram_scheduled_messages")
            .select("scheduled_at")
            .eq("customer_id", customer_id)
            .eq("kind", "follow_up")
            .eq("status", "queued")
            .order("scheduled_at")
            .limit(1)
            .execute()
        ).data or []
        next_action_at = rows[0]["scheduled_at"] if rows else None
        self.update_lead_fields(customer_id, next_action_at=next_action_at)

    def get_daily_sent_count(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        broadcast_rows = (
            self.client.table("telegram_broadcast_logs")
            .select("id")
            .eq("status", "sent")
            .gte("sent_at", f"{today}T00:00:00+00:00")
            .execute()
        ).data or []
        scheduled_rows = (
            self.client.table("telegram_scheduled_recipients")
            .select("id")
            .eq("status", "sent")
            .gte("sent_at", f"{today}T00:00:00+00:00")
            .execute()
        ).data or []
        return len(broadcast_rows) + len(scheduled_rows)

    def get_setting_int(self, key: str, default: int) -> int:
        rows = (
            self.client.table("crm_settings")
            .select("value")
            .eq("key", key)
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            return default
        try:
            return int(rows[0]["value"])
        except Exception:
            return default

    def get_setting(self, key: str, default: str = "") -> str:
        rows = (
            self.client.table("crm_settings")
            .select("value")
            .eq("key", key)
            .limit(1)
            .execute()
        ).data or []
        return str(rows[0]["value"]) if rows else default

    def set_setting(self, key: str, value: str) -> None:
        self.client.table("crm_settings").upsert(
            {
                "key": key,
                "value": value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="key",
        ).execute()

    def search_customers(self, text: str, limit: int = 10) -> list[dict[str, Any]]:
        raw_query = text.strip().lstrip("@")[:100]
        query = "".join(
            char
            for char in raw_query
            if char.isalnum() or char in {"_", "-", ".", " ", "'"}
        ).strip()
        if not query:
            return []
        if query.isdigit():
            return (
                self.client.table("telegram_customers")
                .select("*")
                .eq("telegram_user_id", int(query))
                .limit(limit)
                .execute()
            ).data or []
        return (
            self.client.table("telegram_customers")
            .select("*")
            .or_(f"full_name.ilike.%{query}%,username.ilike.%{query}%")
            .limit(limit)
            .execute()
        ).data or []

    def set_customer_status(self, telegram_user_id: int, status: str) -> None:
        self.client.table("telegram_customers").update(
            {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("telegram_user_id", telegram_user_id).execute()

    def recent_broadcasts(self, limit: int = 5) -> list[dict[str, Any]]:
        return (
            self.client.table("telegram_broadcasts")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data or []
