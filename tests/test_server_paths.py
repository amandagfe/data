import http.client
import threading
import unittest

from server import TelegramConfig, is_public_path, make_server


class PublicPathTests(unittest.TestCase):
    def test_site_files_are_public(self):
        for path in ("/", "/index.html", "/app.js", "/i18n.js", "/style.css",
                     "/assets/logo.webp", "/data/catalog.json", "/data/models.json"):
            self.assertTrue(is_public_path(path), path)

    def test_secrets_and_internals_are_private_even_when_encoded(self):
        for path in ("/.env", "/%2Eenv", "/%2eenv", "/.git/config", "/%2egit/config",
                     "/.venv/pyvenv.cfg", "/server.py", "/tests/x.py", "/scripts/a.py",
                     "/config/telegram.env.example", "/docs/modelos.md",
                     "/data/runs/weather/x/ledger.sqlite", "/data/sources/m.json",
                     "/assets/../.env", "/assets/%2E%2E/.env", "/data\\..\\.env"):
            self.assertFalse(is_public_path(path), path)


class ServerBlocksSecretsTests(unittest.TestCase):
    def test_get_and_head_cannot_read_env(self):
        config = TelegramConfig(requested=False, token="", chat_id="", allowed_origins=())
        server = make_server("127.0.0.1", 0, config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        for method, path in (("GET", "/%2Eenv"), ("HEAD", "/.env"), ("GET", "/.env")):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path)
            response = conn.getresponse(); response.read(); conn.close()
            self.assertEqual(response.status, 404, f"{method} {path}")


if __name__ == "__main__":
    unittest.main()
