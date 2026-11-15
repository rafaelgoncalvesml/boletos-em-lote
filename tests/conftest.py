from datetime import date

import pytest

from boletos.config import Config

HOJE = date(2026, 11, 15)
CPF_1 = "11144477735"
CPF_2 = "52998224725"
CNPJ_1 = "11222333000181"


@pytest.fixture
def hoje():
    return HOJE


@pytest.fixture
def cfg(tmp_path):
    return Config(
        pausa_entre_req_ms=0,
        db_path=tmp_path / "teste.db",
        rascunhos_dir=tmp_path / "rascunhos",
        logs_dir=tmp_path / "logs",
    )
