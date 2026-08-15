from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from app.lead_templates import (
    available_quick_replies,
    build_followup_plan,
    format_price,
    render_template,
)


def config(**overrides):
    values = {
        "service_price_uzs": 39000,
        "sample_article_url": "https://bunyodkor.com/sample",
        "public_offer_url": "https://bunyodkor.com/offer",
        "application_form_url": "",
        "payment_details": "",
        "follow_up_first_hours": 2,
        "follow_up_second_hours": 24,
        "follow_up_final_hours": 72,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


CUSTOMER = {
    "id": "customer-id",
    "telegram_user_id": 123,
    "full_name": "Gulnoza Ibodullayeva",
    "username": "gulnoza_01",
    "published_url": None,
}


class LeadTemplateTests(TestCase):
    def test_price_is_formatted_for_uzbek_readability(self) -> None:
        self.assertEqual(format_price(39000), "39 000 so‘m")

    def test_welcome_is_short_and_uses_customer_name(self) -> None:
        text = render_template("welcome", CUSTOMER, config())
        self.assertIn("Assalomu alaykum, Gulnoza!", text)
        self.assertIn("39 000 so‘m", text)
        self.assertNotIn("Wikipedia", text)
        self.assertNotIn("ko‘k nishon", text)

    def test_unconfigured_sensitive_templates_are_hidden(self) -> None:
        keys = available_quick_replies(CUSTOMER, config())
        self.assertNotIn("payment_request", keys)
        self.assertNotIn("questionnaire", keys)

    def test_configured_templates_are_available(self) -> None:
        keys = available_quick_replies(
            CUSTOMER,
            config(
                payment_details="Payment instructions",
                application_form_url="https://bunyodkor.com/application",
            ),
        )
        self.assertIn("payment_request", keys)
        self.assertIn("questionnaire", keys)

    def test_followup_plan_is_ordered_and_personalized(self) -> None:
        start = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
        plan = build_followup_plan(CUSTOMER, config(), now=start)
        self.assertEqual([item["sequence_step"] for item in plan], [1, 2, 3])
        self.assertEqual(
            [int((item["scheduled_at"] - start).total_seconds() / 3600) for item in plan],
            [2, 24, 72],
        )
        self.assertTrue(all("Gulnoza" in item["message_text"] for item in plan))
