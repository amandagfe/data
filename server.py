#!/usr/bin/env python3
"""Servidor local do site e ponte segura, opcional, para o Telegram.

O token e o destinatario existem somente no ambiente do processo. O cliente
envia um conjunto pequeno de campos validados; nunca envia token, chat_id ou
texto livre para o Telegram.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 4096
RATE_LIMIT_COUNT = 3
RATE_LIMIT_WINDOW_SECONDS = 10 * 60
VALID_BANDS = {"normal", "elev", "alto", "muito"}
DATE_RE = re.compile(r"^\d{8}$")
SECRET_ENV_KEYS = {
    "TELEGRAM_ALERTS_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_ALLOWED_ORIGINS",
}


# Lista de permissão: só o que o site carrega. O caminho é decodificado antes
# da checagem para que "/%2Eenv" e semelhantes não escapem do filtro.
PUBLIC_FILES = {"", "index.html", "app.js", "i18n.js", "style.css", "favicon.ico"}
PUBLIC_DIRS = {"assets", "data"}
PRIVATE_DATA_DIRS = {"runs", "sources", "grids", "releases"}


def is_public_path(raw_path: str) -> bool:
    path = urllib.parse.unquote(raw_path)
    if "\\" in path or "\x00" in path:
        return False
    parts = [part for part in path.split("/") if part]
    if any(part.startswith(".") for part in parts):
        return False  # .env, .git, .venv, "..", etc.
    if not parts:
        return True
    if len(parts) == 1:
        return parts[0] in PUBLIC_FILES
    if parts[0] not in PUBLIC_DIRS:
        return False
    return not (parts[0] == "data" and parts[1] in PRIVATE_DATA_DIRS)


def load_environment_file(path: Path) -> None:
    """Carrega somente chaves Telegram de arquivo local com permissão privada."""
    if not path.exists():
        return
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"{path}: use chmod 600 antes de iniciar")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in SECRET_ENV_KEYS:
            os.environ.setdefault(key, value.strip())


@dataclass(frozen=True)
class TelegramConfig:
    requested: bool
    token: str
    chat_id: str
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "TelegramConfig":
        origins = tuple(
            item.strip().rstrip("/")
            for item in os.getenv("TELEGRAM_ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        )
        return cls(
            requested=os.getenv("TELEGRAM_ALERTS_ENABLED") == "1",
            token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            allowed_origins=origins,
        )

    @property
    def reason(self) -> str:
        if not self.requested:
            return "disabled_by_operator"
        if not self.token or not self.chat_id:
            return "missing_server_configuration"
        return "ready"

    @property
    def enabled(self) -> bool:
        return self.reason == "ready"

    def public_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "reason": self.reason,
            "coordinate_precision_decimals": 2,
            "rate_limit": {
                "requests": RATE_LIMIT_COUNT,
                "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
            },
        }


class RateLimiter:
    def __init__(self) -> None:
        self._entries: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            recent = [
                stamp
                for stamp in self._entries.get(key, [])
                if current - stamp < RATE_LIMIT_WINDOW_SECONDS
            ]
            if len(recent) >= RATE_LIMIT_COUNT:
                self._entries[key] = recent
                return False
            recent.append(current)
            self._entries[key] = recent
            return True


def _plain_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid_{field}")
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > maximum:
        raise ValueError(f"invalid_{field}")
    return cleaned


def validate_notice(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    allowed = {"place", "latitude", "longitude", "score", "band", "data_reference"}
    if set(payload) - allowed:
        raise ValueError("unexpected_field")

    place = _plain_text(payload.get("place"), "place", 120)
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
        score = int(payload.get("score"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_number") from exc
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("invalid_coordinates")
    if not 0 <= score <= 100:
        raise ValueError("invalid_score")

    band = _plain_text(payload.get("band"), "band", 12)
    if band not in VALID_BANDS:
        raise ValueError("invalid_band")
    data_reference = _plain_text(payload.get("data_reference"), "data_reference", 8)
    if not DATE_RE.fullmatch(data_reference):
        raise ValueError("invalid_data_reference")

    return {
        "place": place,
        "latitude": round(latitude, 2),
        "longitude": round(longitude, 2),
        "score": score,
        "band": band,
        "data_reference": data_reference,
    }


def build_message(notice: dict[str, Any]) -> str:
    date = notice["data_reference"]
    date_iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    return "\n".join(
        [
            "Data Detectives — aviso técnico solicitado pelo usuário",
            f"Local: {notice['place']}",
            f"Coordenada aproximada: {notice['latitude']:.2f}, {notice['longitude']:.2f}",
            f"Score meteorológico: {notice['score']}/100 (faixa {notice['band']})",
            f"Referência dos dados: {date_iso}",
            "Índice experimental regional; não é risco, probabilidade nem alerta oficial.",
        ]
    )


def send_telegram(config: TelegramConfig, message: str) -> None:
    data = urllib.parse.urlencode(
        {"chat_id": config.chat_id, "text": message, "disable_web_page_preview": "true"}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{config.token}/sendMessage",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        # A excecao pode conter a URL com o token. Nao a registre nem a devolva.
        raise RuntimeError("telegram_unavailable") from None
    if not result.get("ok"):
        raise RuntimeError("telegram_rejected")


class SiteHandler(SimpleHTTPRequestHandler):
    server_version = "DataDetectives/1.0"

    @property
    def config(self) -> TelegramConfig:
        return self.server.telegram_config  # type: ignore[attr-defined]

    @property
    def limiter(self) -> RateLimiter:
        return self.server.rate_limiter  # type: ignore[attr-defined]

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        normalized = origin.rstrip("/")
        if self.config.allowed_origins:
            return normalized in self.config.allowed_origins
        parsed = urllib.parse.urlparse(normalized)
        return parsed.scheme in {"http", "https"} and parsed.netloc == self.headers.get("Host")

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/telegram/status":
            self._json(HTTPStatus.OK, self.config.public_status())
            return
        if path == "/healthz":
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if not is_public_path(path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if not is_public_path(urllib.parse.urlparse(self.path).path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_HEAD()

    def do_POST(self) -> None:  # noqa: N802
        if urllib.parse.urlparse(self.path).path != "/api/telegram/notices":
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self.config.enabled:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": self.config.reason},
            )
            return
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "origin_not_allowed"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"ok": False, "error": "json_required"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size <= 0 or size > MAX_BODY_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "invalid_size"})
            return
        client = self.client_address[0]
        if not self.limiter.allow(client):
            self._json(HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": "rate_limited"})
            return
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            notice = validate_notice(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            code = str(exc) if isinstance(exc, ValueError) else "invalid_json"
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": code})
            return
        try:
            send_telegram(self.config, build_message(notice))
        except RuntimeError:
            self._json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": "telegram_unavailable"})
            return
        self._json(HTTPStatus.OK, {"ok": True})

    def list_directory(self, path: str):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def log_message(self, format: str, *args: Any) -> None:
        # Metodo e caminho sao suficientes; nao inclua payload, cabecalhos ou segredos.
        super().log_message("%s %s", self.command, urllib.parse.urlparse(self.path).path)


def make_server(host: str, port: int, config: TelegramConfig | None = None) -> ThreadingHTTPServer:
    handler = lambda *args, **kwargs: SiteHandler(*args, directory=str(ROOT), **kwargs)
    server = ThreadingHTTPServer((host, port), handler)
    server.telegram_config = config or TelegramConfig.from_environment()  # type: ignore[attr-defined]
    server.rate_limiter = RateLimiter()  # type: ignore[attr-defined]
    return server


def main() -> None:
    env_path = Path(os.getenv("DD_ENV_FILE", str(ROOT / ".env"))).resolve()
    load_environment_file(env_path)
    host = os.getenv("DD_HOST", "127.0.0.1")
    port = int(os.getenv("DD_PORT", "8000"))
    server = make_server(host, port)
    status = server.telegram_config.public_status()  # type: ignore[attr-defined]
    print(f"Data Detectives: http://{host}:{port} (Telegram: {status['reason']})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
