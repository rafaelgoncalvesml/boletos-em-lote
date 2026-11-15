from __future__ import annotations

import smtplib
import ssl
from email import message_from_bytes, policy
from pathlib import Path
from typing import Protocol


class Sender(Protocol):
    def enviar(self, caminho: Path) -> None: ...


class SmtpSender:
    def __init__(
        self, host: str, porta: int, usuario: str | None = None, senha: str | None = None, timeout: float = 15.0
    ):
        self._host = host
        self._porta = porta
        self._usuario = usuario
        self._senha = senha
        self._timeout = timeout

    def enviar(self, caminho: Path) -> None:
        msg = message_from_bytes(Path(caminho).read_bytes(), policy=policy.SMTP)
        with smtplib.SMTP(self._host, self._porta, timeout=self._timeout) as smtp:
            if self._usuario:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self._usuario, self._senha)
            smtp.send_message(msg)
