from datetime import datetime, timezone
from unittest import TestCase

from app.scheduling import (
    format_local_datetime,
    normalize_usernames,
    parse_local_datetime,
)


class SchedulingTests(TestCase):
    def test_normalize_usernames_deduplicates_case_insensitively(self) -> None:
        usernames, invalid = normalize_usernames("@Ali_01, ali_01\n@Vali_02")
        self.assertEqual(usernames, ["ali_01", "vali_02"])
        self.assertEqual(invalid, [])

    def test_normalize_usernames_returns_invalid_tokens(self) -> None:
        usernames, invalid = normalize_usernames("@valid_name, bad!, @ab")
        self.assertEqual(usernames, ["valid_name"])
        self.assertEqual(invalid, ["bad!", "@ab"])

    def test_parse_tashkent_time_to_utc(self) -> None:
        value = parse_local_datetime("2026-08-20 14:30:15", "Asia/Tashkent")
        self.assertEqual(
            value,
            datetime(2026, 8, 20, 9, 30, 15, tzinfo=timezone.utc),
        )

    def test_format_utc_as_tashkent_time(self) -> None:
        value = datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)
        self.assertEqual(
            format_local_datetime(value, "Asia/Tashkent"),
            "2026-08-20 14:30",
        )

    def test_rejects_invalid_datetime(self) -> None:
        self.assertIsNone(parse_local_datetime("ertaga tushdan keyin"))
