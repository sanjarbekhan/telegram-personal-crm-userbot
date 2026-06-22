from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from supabase import Client, create_client

from app.config import Config


class Database:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client: Client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

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

        # fallback: fetch existing record
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
            payload, on_conflict="telegram_user_id,message_id"
        ).execute()

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

        customers = (
            self.client.table("telegram_customers")
            .select("*")
            .in_("telegram_user_id", user_ids)
            .neq("status", "do_not_contact")
            .execute()
        ).data or []
        return customers

    def create_broadcast(
        self,
        target_date: str,
        message_text: str,
        customers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        broadcast = (
            self.client.table("telegram_broadcasts")
            .insert(
                {
                    "target_date": target_date,
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
                "customer_id": c["id"],
                "telegram_user_id": c["telegram_user_id"],
                "status": "pending",
            }
            for c in customers
        ]
        if logs:
            self.client.table("telegram_broadcast_logs").upsert(
                logs, on_conflict="broadcast_id,telegram_user_id"
            ).execute()
        return broadcast

    def get_next_pending_log(self) -> dict[str, Any] | None:
        logs = (
            self.client.table("telegram_broadcast_logs")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(1)
            .execute()
        ).data or []
        return logs[0] if logs else None

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

    def update_log(self, log_id: str, status: str, error_text: str | None = None) -> None:
        payload: dict[str, Any] = {"status": status}
        if status == "sent":
            payload["sent_at"] = datetime.now(timezone.utc).isoformat()
        if error_text:
            payload["error_text"] = error_text[:1000]
        self.client.table("telegram_broadcast_logs").update(payload).eq("id", log_id).execute()

    def mark_broadcast_running(self, broadcast_id: str) -> None:
        broadcast = self.get_broadcast(broadcast_id)
        payload: dict[str, Any] = {"status": "running"}
        if broadcast and not broadcast.get("started_at"):
            payload["started_at"] = datetime.now(timezone.utc).isoformat()
        self.client.table("telegram_broadcasts").update(payload).eq("id", broadcast_id).execute()

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
        pending = sum(1 for row in logs if row["status"] in ("pending", "processing"))
        payload: dict[str, Any] = counts.copy()
        if pending == 0:
            payload["status"] = "finished"
            payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.client.table("telegram_broadcasts").update(payload).eq("id", broadcast_id).execute()
        return counts

    def get_daily_sent_count(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        logs = (
            self.client.table("telegram_broadcast_logs")
            .select("id")
            .eq("status", "sent")
            .gte("sent_at", f"{today}T00:00:00+00:00")
            .execute()
        ).data or []
        return len(logs)

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

    def search_customers(self, text: str, limit: int = 10) -> list[dict[str, Any]]:
        # Supabase ilike works well for username/full_name. Numeric search is handled separately.
        q = text.strip().lstrip("@")
        if q.isdigit():
            rows = (
                self.client.table("telegram_customers")
                .select("*")
                .eq("telegram_user_id", int(q))
                .limit(limit)
                .execute()
            ).data or []
            return rows
        rows = (
            self.client.table("telegram_customers")
            .select("*")
            .or_(f"full_name.ilike.%{q}%,username.ilike.%{q}%")
            .limit(limit)
            .execute()
        ).data or []
        return rows

    def set_customer_status(self, telegram_user_id: int, status: str) -> None:
        self.client.table("telegram_customers").update(
            {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("telegram_user_id", telegram_user_id).execute()

    def recent_broadcasts(self, limit: int = 5) -> list[dict[str, Any]]:
        return (
            self.client.table("telegram_broadcasts")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data or []
