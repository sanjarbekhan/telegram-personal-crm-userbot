from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar


T = TypeVar("T")

TRANSIENT_ERROR_MARKERS = (
    "server disconnected",
    "connection closed",
    "connection reset",
    "connection aborted",
    "remoteprotocolerror",
    "remote protocol error",
    "temporarily unavailable",
    "network is unreachable",
    "timed out",
    "timeout",
)


def is_transient_connection_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, OSError, TimeoutError, asyncio.TimeoutError)):
        return True
    error_text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in error_text for marker in TRANSIENT_ERROR_MARKERS)


def call_with_retry(
    func: Callable[..., T],
    /,
    *args: Any,
    attempts: int = 3,
    delays: tuple[float, ...] = (0.5, 1.5),
    **kwargs: Any,
) -> T:
    for attempt in range(attempts):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not is_transient_connection_error(exc) or attempt == attempts - 1:
                raise
            time.sleep(delays[min(attempt, len(delays) - 1)])
    raise RuntimeError("Retry loop ended unexpectedly")


async def to_thread_with_retry(
    func: Callable[..., T],
    /,
    *args: Any,
    **kwargs: Any,
) -> T:
    return await asyncio.to_thread(call_with_retry, func, *args, **kwargs)


async def async_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    delays: tuple[float, ...] = (1.0, 3.0),
) -> T:
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            if not is_transient_connection_error(exc) or attempt == attempts - 1:
                raise
            await asyncio.sleep(delays[min(attempt, len(delays) - 1)])
    raise RuntimeError("Retry loop ended unexpectedly")
