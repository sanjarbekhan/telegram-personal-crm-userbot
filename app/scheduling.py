from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
MAX_SCHEDULE_RECIPIENTS = 50


def normalize_usernames(raw: str) -> tuple[list[str], list[str]]:
    """Return unique valid usernames and invalid tokens."""
    tokens = re.split(r"[\s,;]+", raw.strip())
    usernames: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        if not token:
            continue
        username = token.strip().lstrip("@").lower()
        if not USERNAME_RE.fullmatch(username):
            invalid.append(token[:40])
            continue
        if username in seen:
            continue
        seen.add(username)
        usernames.append(username)

    return usernames, invalid


def parse_local_datetime(
    raw: str,
    timezone_name: str = "Asia/Tashkent",
) -> datetime | None:
    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_zone = timezone.utc

    value = raw.strip()
    parsed: datetime | None = None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ):
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue

    if parsed is None:
        return None
    return parsed.replace(tzinfo=local_zone).astimezone(timezone.utc)


def format_local_datetime(
    value: datetime | str,
    timezone_name: str = "Asia/Tashkent",
) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_zone = timezone.utc
    local_value = value.astimezone(local_zone)
    fmt = "%Y-%m-%d %H:%M:%S" if local_value.second else "%Y-%m-%d %H:%M"
    return local_value.strftime(fmt)
