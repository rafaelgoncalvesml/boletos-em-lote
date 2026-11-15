from dataclasses import replace
from datetime import date

import pytest

from boletos.config import Config
from boletos.models import Cobranca, Estado, LinhaValida, chave_da_linha
from boletos.store.db import Banco

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


@pytest.fixture
def fazer_linha():
    def _fazer(i=1, **mudancas):
        base = dict(
            linha=i + 1,
            nome=f"Cliente {i}",
            documento=f"{i:011d}",
            email=f"cliente{i}@exemplo.test",
            valor_cent=125000,
            vencimento=date(2026, 12, 15),
            competencia="2026-11",
            descricao="Mensalidade de novembro",
        )
        base.update(mudancas)
        return LinhaValida(**base)

    return _fazer


@pytest.fixture
def fazer_cobranca():
    def _fazer(**mudancas):
        base = Cobranca(
            id=1,
            lote_id=1,
            chave_idem="c" * 64,
            cliente_nome="Mariana Souza Ltda",
            cliente_doc=CPF_1,
            cliente_email="financeiro@exemplo.test",
            competencia="2026-11",
            valor_cent=125000,
            vencimento="2026-12-15",
            descricao="Mensalidade de novembro",
            estado=Estado.EMITIDA,
            etapa_falha=None,
            id_cliente_gw="cus_1",
            id_cobranca_gw="pay_1",
            link_boleto="https://sandbox.exemplo.test/boleto/00001",
            linha_digitavel="00000.00000 00000.000000 00000.000000 0 00000000000000",
            criado_em="2026-11-15T10:00:00+00:00",
            atualizado_em="2026-11-15T10:00:00+00:00",
        )
        return replace(base, **mudancas)

    return _fazer


@pytest.fixture
def banco(tmp_path):
    b = Banco.abrir(tmp_path / "teste.db")
    yield b
    b.close()


@pytest.fixture
def lote_com(banco):
    def _criar(linhas):
        lote_id = banco.criar_lote("teste.csv", "h" * 64, len(linhas), 0)
        for linha in linhas:
            banco.inserir_cobranca(lote_id, linha, chave_da_linha(linha))
        return lote_id

    return _criar
