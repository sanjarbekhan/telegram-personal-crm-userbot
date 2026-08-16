from unittest import TestCase

from app.retry import call_with_retry, is_transient_connection_error


class RetryTests(TestCase):
    def test_server_disconnected_is_transient(self) -> None:
        self.assertTrue(is_transient_connection_error(RuntimeError("Server disconnected")))

    def test_transient_operation_is_retried(self) -> None:
        calls = 0

        def flaky_operation() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("Server disconnected")
            return "ok"

        result = call_with_retry(
            flaky_operation,
            attempts=3,
            delays=(0, 0),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls, 3)

    def test_business_error_is_not_retried(self) -> None:
        calls = 0

        def invalid_operation() -> None:
            nonlocal calls
            calls += 1
            raise ValueError("Username noto‘g‘ri")

        with self.assertRaises(ValueError):
            call_with_retry(invalid_operation, attempts=3, delays=(0, 0))

        self.assertEqual(calls, 1)
