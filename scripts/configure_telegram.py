#!/usr/bin/env python3
"""Descobre um grupo recebido pelo bot e grava a configuração local em .env.

O token é lido com getpass, não aparece no terminal e nunca é impresso. Para o
grupo aparecer em getUpdates, adicione o bot ao grupo e envie uma mensagem ou
comando depois disso.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_USERNAME = "data_dectives_bot"
GROUP_TYPES = {"group", "supergroup", "channel"}


def normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def bot_request(token: str, method: str) -> dict:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        # Exceções podem conter a URL e o token. Não as imprima.
        raise RuntimeError("A API do Telegram não respondeu.") from None
    if not payload.get("ok"):
        raise RuntimeError("O Telegram recusou a credencial ou a consulta.")
    return payload


def chats_from_updates(updates: list[dict]) -> list[dict]:
    found: dict[str, dict] = {}
    for update in updates:
        candidates = []
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            if isinstance(update.get(key), dict):
                candidates.append(update[key].get("chat"))
        for key in ("my_chat_member", "chat_member", "chat_join_request"):
            if isinstance(update.get(key), dict):
                candidates.append(update[key].get("chat"))
        for chat in candidates:
            if isinstance(chat, dict) and chat.get("type") in GROUP_TYPES and chat.get("id") is not None:
                found[str(chat["id"])] = chat
    return list(found.values())


def choose_chat(chats: list[dict], wanted: str) -> dict:
    target = normalized(wanted)
    exact = [
        chat
        for chat in chats
        if target in {normalized(chat.get("title")), normalized(chat.get("username"))}
    ]
    partial = [
        chat
        for chat in chats
        if target and target in normalized(" ".join(filter(None, [chat.get("title"), chat.get("username")])))
    ]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(
            "Grupo não encontrado nas atualizações. Adicione o bot ao grupo, envie /start@data_dectives_bot no grupo e execute novamente."
        )
    labels = ", ".join(f"{chat.get('title') or chat.get('username')} ({chat['id']})" for chat in matches)
    raise RuntimeError(f"Mais de um grupo corresponde ao nome: {labels}")


def write_private_env(path: Path, token: str, chat_id: int) -> None:
    content = "\n".join(
        [
            "# Gerado localmente por scripts/configure_telegram.py. Não versionar.",
            "TELEGRAM_ALERTS_ENABLED=1",
            f"TELEGRAM_BOT_TOKEN={token}",
            f"TELEGRAM_CHAT_ID={chat_id}",
            "",
        ]
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="Data Dectives", help="título ou username esperado")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()

    token = getpass.getpass("Token do bot (não será exibido): ").strip()
    if not token:
        raise SystemExit("Token não informado; nada foi gravado.")
    try:
        me = bot_request(token, "getMe")["result"]
        if (me.get("username") or "").casefold() != BOT_USERNAME:
            raise RuntimeError(f"A credencial não pertence a @{BOT_USERNAME}.")
        updates = bot_request(token, "getUpdates?limit=100&allowed_updates=%5B%22message%22,%22channel_post%22,%22my_chat_member%22%5D")
        chat = choose_chat(chats_from_updates(updates["result"]), args.group)
        write_private_env(args.env_file.resolve(), token, int(chat["id"]))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    print(f"Configuração gravada em {args.env_file.resolve()} para {chat.get('title') or chat.get('username')} ({chat['type']}).")
    print("O token não foi exibido. Inicie com: python3 server.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
