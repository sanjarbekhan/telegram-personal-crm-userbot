from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from app.contact_import import scan_private_contacts


class FakeClient:
    def __init__(self, dialogs):
        self.dialogs = dialogs

    async def iter_dialogs(self):
        for dialog in self.dialogs:
            yield dialog


class FakeDatabase:
    def __init__(self):
        self.saved = []

    def upsert_customer(self, telegram_user_id, full_name, username, phone=None):
        self.saved.append((telegram_user_id, full_name, username, phone))
        return {"telegram_user_id": telegram_user_id}


class ContactScanTests(IsolatedAsyncioTestCase):
    async def test_only_human_private_dialog_metadata_is_imported(self) -> None:
        dialogs = [
            SimpleNamespace(
                is_user=True,
                entity=SimpleNamespace(
                    id=101,
                    first_name="Ali",
                    last_name="Valiyev",
                    username="ali_01",
                ),
            ),
            SimpleNamespace(
                is_user=True,
                entity=SimpleNamespace(id=102, first_name="Bot", bot=True),
            ),
            SimpleNamespace(
                is_user=True,
                entity=SimpleNamespace(id=103, first_name="Deleted", deleted=True),
            ),
            SimpleNamespace(is_user=False, entity=object()),
        ]
        db = FakeDatabase()

        telegram_user_ids = await scan_private_contacts(FakeClient(dialogs), db)

        self.assertEqual(telegram_user_ids, [101])
        self.assertEqual(db.saved, [(101, "Ali Valiyev", "ali_01", None)])
