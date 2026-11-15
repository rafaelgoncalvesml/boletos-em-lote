import pytest

from boletos.erros import EntradaRecusada
from boletos.lote import importar
from boletos.models import Estado
from tests.conftest import CNPJ_1, CPF_1, CPF_2

pytestmark = pytest.mark.integration

CAB = "nome,documento,email,valor,vencimento,competencia,descricao"


def _l(nome, doc, valor='"1.250,00"', comp="2026-11"):
    return f"{nome},{doc},{nome.lower()}@exemplo.test,{valor},15/12/2026,{comp},Mensalidade"


@pytest.fixture
def tres(escrever_csv):
    return escrever_csv([_l("Ana", CPF_1), _l("Bia", CPF_2), _l("Cia", CNPJ_1)])


def _total(banco, tabela):
    return banco.con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def test_importar_grava_lote_e_cobrancas_validadas(banco, cfg, hoje, tres):
    r = importar(banco, tres, cfg, hoje)
    assert r.lote_id and len(r.criadas) == 3 and r.rejeicoes == [] and r.novas == 3
    assert banco.contar_por_estado(r.lote_id) == {"validada": 3}


def test_rn10_reimportar_o_mesmo_arquivo_nao_recria_nada(banco, cfg, hoje, tres):
    r1 = importar(banco, tres, cfg, hoje)
    r2 = importar(banco, tres, cfg, hoje)
    assert r2.lote_id != r1.lote_id
    assert r2.criadas == [] and len(r2.existentes) == 3 and r2.novas == 0
    assert any(a.tipo == "arquivo_repetido" for a in r2.avisos)
    assert r2.arquivo_repetido == r1.lote_id
    assert _total(banco, "cobrancas") == 3
    assert all(c.estado == Estado.VALIDADA for _, c in r2.existentes)


def test_rn01_coluna_faltando_recusa_tudo_e_nao_grava(banco, cfg, hoje, escrever_csv):
    arq = escrever_csv([], cabecalho="nome,documento,email,valor,vencimento")
    with pytest.raises(EntradaRecusada, match="competencia"):
        importar(banco, arq, cfg, hoje)
    assert _total(banco, "lotes") == 0 and _total(banco, "cobrancas") == 0


def test_dry_run_nao_grava_nada(banco, cfg, hoje, tres):
    r = importar(banco, tres, cfg, hoje, dry_run=True)
    assert r.dry_run and r.lote_id is None and r.novas == 3 and r.criadas == []
    assert _total(banco, "lotes") == 0 and _total(banco, "cobrancas") == 0


def test_rejeicoes_ficam_no_banco_e_nao_bloqueiam_as_demais(banco, cfg, hoje, escrever_csv):
    arq = escrever_csv([_l("Ana", CPF_1), _l("Ruim", "123")])
    r = importar(banco, arq, cfg, hoje)
    assert len(r.criadas) == 1 and len(r.rejeicoes) == 1
    assert banco.rejeicoes(r.lote_id)[0].coluna == "documento"
    assert banco.obter_lote(r.lote_id)["linhas_rejeitadas"] == 1


def test_a2_mesma_competencia_com_valor_diferente_entre_lotes_avisa_e_cria(banco, cfg, hoje, escrever_csv):
    importar(banco, escrever_csv([_l("Ana", CPF_1)], nome="a.csv"), cfg, hoje)
    r = importar(banco, escrever_csv([_l("Ana", CPF_1, valor='"1.300,00"')], nome="b.csv"), cfg, hoje)
    assert len(r.criadas) == 1
    assert [a.tipo for a in r.avisos] == ["competencia_repetida"]
    tipos = [e["tipo"] for e in banco.eventos(r.lote_id)]
    assert "aviso_competencia_repetida" in tipos


def test_a2_dentro_do_mesmo_arquivo_tambem_vira_evento(banco, cfg, hoje, escrever_csv):
    arq = escrever_csv([_l("Ana", CPF_1), _l("Ana", CPF_1, valor='"1.300,00"')])
    r = importar(banco, arq, cfg, hoje)
    assert len(r.criadas) == 2
    assert sum(a.tipo == "competencia_repetida" for a in r.avisos) == 1
    assert [e["tipo"] for e in banco.eventos(r.lote_id)].count("aviso_competencia_repetida") == 1
