import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from boletos.gateway.fake import FakeGateway
from boletos.lote import analisar
from boletos.models import Cliente

pytestmark = pytest.mark.integration

RAIZ = Path(__file__).resolve().parents[2]


def _carregar_script():
    spec = importlib.util.spec_from_file_location("gerar_exemplo", RAIZ / "scripts" / "gerar_exemplo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_marco1_planilha_de_exemplo_vira_lote_validado_e_emite_no_fake(tmp_path, cfg, hoje, fazer_cobranca):
    arq = tmp_path / "exemplo.csv"
    _carregar_script().escrever(arq, hoje)

    analise = analisar(arq, cfg, hoje)
    assert len(analise.itens) == 20
    assert len(analise.rejeicoes) == 4  # listadas com linha, coluna e motivo
    assert all(r.motivo for r in analise.rejeicoes)

    gw = FakeGateway()
    emissoes = []
    for i, item in enumerate(analise.itens, start=1):
        d = item.dados
        id_cliente = gw.criar_cliente(Cliente(d.nome, d.documento, d.email))
        cobranca = replace(
            fazer_cobranca(),
            id=i,
            chave_idem=item.chave,
            cliente_doc=d.documento,
            valor_cent=d.valor_cent,
            vencimento=d.vencimento.isoformat(),
            id_cliente_gw=id_cliente,
            id_cobranca_gw=None,
            link_boleto=None,
        )
        emissoes.append(gw.emitir(cobranca))
    assert gw.total_emitido == 20
    assert len({e.id_gw for e in emissoes}) == 20
