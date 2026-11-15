from __future__ import annotations

import smtplib
import socket
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
        self._nome_local: str | None = None

    def enviar(self, caminho: Path) -> None:
        msg = message_from_bytes(Path(caminho).read_bytes(), policy=policy.SMTP)
        # o smtplib chama getfqdn a cada conexão e isso custa ~1 s no Windows; um lote inteiro usa o mesmo nome
        if self._nome_local is None:
            self._nome_local = socket.getfqdn()
        with smtplib.SMTP(self._host, self._porta, local_hostname=self._nome_local, timeout=self._timeout) as smtp:
            if self._usuario:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self._usuario, self._senha)
            smtp.send_message(msg)
