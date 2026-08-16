from pathlib import Path
from unittest import TestCase


SCHEMA = (Path(__file__).parents[1] / "sql" / "schema.sql").read_text(
    encoding="utf-8"
).lower()


class SchemaSecurityTests(TestCase):
    def test_every_server_table_has_rls_enabled(self) -> None:
        tables = [
            "telegram_customers",
            "telegram_chat_messages",
            "telegram_broadcasts",
            "telegram_broadcast_logs",
            "telegram_scheduled_messages",
            "telegram_scheduled_recipients",
            "crm_settings",
        ]
        for table in tables:
            with self.subTest(table=table):
                self.assertIn(f"alter table {table} enable row level security", SCHEMA)

    def test_public_client_roles_are_revoked(self) -> None:
        self.assertNotIn("grant select, insert, update, delete on table telegram_customers to anon", SCHEMA)
        self.assertIn(
            "revoke all on table telegram_customers from anon, authenticated",
            SCHEMA,
        )

    def test_service_role_is_explicitly_granted(self) -> None:
        self.assertIn(
            "grant select, insert, update, delete on table telegram_customers to service_role",
            SCHEMA,
        )
        self.assertIn(
            "grant select, insert, update, delete on table telegram_scheduled_messages to service_role",
            SCHEMA,
        )

    def test_professional_crm_fields_exist(self) -> None:
        for field in (
            "pipeline_status",
            "next_action_at",
            "payment_status",
            "application_complete",
            "consent_received",
            "cancel_on_reply",
        ):
            with self.subTest(field=field):
                self.assertIn(field, SCHEMA)

    def test_all_contacts_broadcast_scope_is_supported(self) -> None:
        self.assertIn("target_scope", SCHEMA)
        self.assertIn("target_scope in ('date', 'all')", SCHEMA)
        self.assertIn(
            "alter table telegram_broadcasts alter column target_date drop not null",
            SCHEMA,
        )
