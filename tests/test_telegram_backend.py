import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import (
    RATE_LIMIT_COUNT,
    RateLimiter,
    TelegramConfig,
    build_message,
    load_environment_file,
    validate_notice,
)


class TelegramBackendTests(unittest.TestCase):
    def test_token_and_destination_never_appear_in_public_status(self):
        env = {
            "TELEGRAM_ALERTS_ENABLED": "1",
            "TELEGRAM_BOT_TOKEN": "not-a-real-token",
            "TELEGRAM_CHAT_ID": "not-a-real-chat",
        }
        with patch.dict(os.environ, env, clear=True):
            config = TelegramConfig.from_environment()
        self.assertTrue(config.enabled)
        self.assertEqual(config.reason, "ready")
        self.assertNotIn("token", config.public_status())
        self.assertNotIn("chat_id", config.public_status())

    def test_valid_notice_is_rounded_and_message_is_fixed(self):
        notice = validate_notice(
            {
                "place": "Petrópolis, RJ",
                "latitude": -22.50501,
                "longitude": -43.17861,
                "score": 63,
                "band": "elev",
                "data_reference": "20261114",
            }
        )
        self.assertEqual(notice["latitude"], -22.51)
        self.assertEqual(notice["longitude"], -43.18)
        message = build_message(notice)
        self.assertIn("63/100", message)
        self.assertIn("não é risco, probabilidade nem alerta oficial", message)

    def test_rejects_free_text_and_invalid_ranges(self):
        base = {
            "place": "Petrópolis",
            "latitude": -22.5,
            "longitude": -43.1,
            "score": 63,
            "band": "elev",
            "data_reference": "20261114",
        }
        with self.assertRaisesRegex(ValueError, "unexpected_field"):
            validate_notice({**base, "message": "texto livre"})
        with self.assertRaisesRegex(ValueError, "invalid_coordinates"):
            validate_notice({**base, "latitude": 91})

    def test_rate_limit(self):
        limiter = RateLimiter()
        for n in range(RATE_LIMIT_COUNT):
            self.assertTrue(limiter.allow("client", now=float(n)))
        self.assertFalse(limiter.allow("client", now=4.0))

    def test_private_environment_file_is_loaded_without_public_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "TELEGRAM_ALERTS_ENABLED=1\nTELEGRAM_BOT_TOKEN=test-only\nTELEGRAM_CHAT_ID=-1001\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            with patch.dict(os.environ, {}, clear=True):
                load_environment_file(path)
                config = TelegramConfig.from_environment()
            self.assertTrue(config.enabled)
            self.assertNotIn("test-only", str(config.public_status()))

    def test_environment_file_rejects_public_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("TELEGRAM_BOT_TOKEN=test-only\n", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                load_environment_file(path)


if __name__ == "__main__":
    unittest.main()
