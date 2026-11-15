import importlib.util
import socket
from datetime import date
from pathlib import Path

import pytest
from aiosmtpd.controller import Controller

RAIZ = Path(__file__).resolve().parents[2]


def carregar_script():
    spec = importlib.util.spec_from_file_location("gerar_exemplo", RAIZ / "scripts" / "gerar_exemplo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for var in ("ASAAS_API_KEY", "ANTHROPIC_API_KEY", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BOLETOS_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BOLETOS_RASCUNHOS", str(tmp_path / "rascunhos"))
    monkeypatch.setenv("BOLETOS_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("PAUSA_ENTRE_REQ_MS", "0")
    return tmp_path


@pytest.fixture
def planilha(ambiente):
    caminho = ambiente / "clientes.csv"
    carregar_script().escrever(caminho, date.today())
    return caminho


class Captura:
    def __init__(self):
        self.envelopes = []

    async def handle_DATA(self, server, session, envelope):
        self.envelopes.append(envelope)
        return "250 Message accepted for delivery"


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servidor_smtp():
    captura = Captura()
    porta = porta_livre()
    controller = Controller(captura, hostname="127.0.0.1", port=porta)
    controller.start()
    yield captura, porta
    controller.stop()
