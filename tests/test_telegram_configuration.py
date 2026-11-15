import tempfile
import unittest
from pathlib import Path

from scripts.configure_telegram import chats_from_updates, choose_chat, write_private_env


class TelegramConfigurationTests(unittest.TestCase):
    def test_only_group_like_chats_are_candidates(self):
        updates = [
            {"message": {"chat": {"id": 1, "type": "private", "username": "edatadetectives"}}},
            {"my_chat_member": {"chat": {"id": -1002, "type": "supergroup", "title": "eDataDetectives"}}},
        ]
        chats = chats_from_updates(updates)
        self.assertEqual([chat["id"] for chat in chats], [-1002])
        self.assertEqual(choose_chat(chats, "edatadetectives")["id"], -1002)

    def test_written_configuration_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            write_private_env(path, "test-only", -1002)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn("TELEGRAM_CHAT_ID=-1002", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
