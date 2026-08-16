from __future__ import annotations

import asyncio
from typing import Any


def contact_full_name(user: Any) -> str:
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join(part for part in parts if part) or "Unknown"


def is_eligible_private_contact(user: Any) -> bool:
    return bool(
        user
        and not getattr(user, "bot", False)
        and not getattr(user, "is_self", False)
        and not getattr(user, "deleted", False)
    )


async def scan_private_contacts(client: Any, db: Any) -> int:
    """Import only human private-dialog metadata, never historical message text."""
    saved_count = 0

    async for dialog in client.iter_dialogs():
        if not getattr(dialog, "is_user", False):
            continue
        entity = getattr(dialog, "entity", None)
        if not is_eligible_private_contact(entity):
            continue

        await asyncio.to_thread(
            db.upsert_customer,
            entity.id,
            contact_full_name(entity),
            getattr(entity, "username", None),
            getattr(entity, "phone", None),
        )
        saved_count += 1

    return saved_count
