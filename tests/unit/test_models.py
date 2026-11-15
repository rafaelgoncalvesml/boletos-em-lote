from datetime import date

from boletos.models import TRANSICOES, Estado, chave_da_linha, chave_idem


def test_rn09_chave_estavel_e_sensivel_a_cada_campo():
    base = chave_idem("11144477735", "2026-11", 125000, "2026-12-15")
    assert base == chave_idem("11144477735", "2026-11", 125000, "2026-12-15")
    assert len(base) == 64
    for outra in (
        chave_idem("52998224725", "2026-11", 125000, "2026-12-15"),
        chave_idem("11144477735", "2026-12", 125000, "2026-12-15"),
        chave_idem("11144477735", "2026-11", 125001, "2026-12-15"),
        chave_idem("11144477735", "2026-11", 125000, "2026-12-16"),
    ):
        assert outra != base


def test_chave_da_linha_usa_vencimento_iso(fazer_linha):
    linha = fazer_linha(1, vencimento=date(2026, 12, 15))
    assert chave_da_linha(linha) == chave_idem(linha.documento, linha.competencia, linha.valor_cent, "2026-12-15")


def test_transicoes_da_planta():
    assert TRANSICOES[Estado.VALIDADA] == {Estado.EMITIDA, Estado.ERRO}
    assert TRANSICOES[Estado.EMITIDA] == {Estado.RASCUNHO, Estado.ERRO}
    assert TRANSICOES[Estado.RASCUNHO] == {Estado.APROVADA, Estado.ERRO}
    assert TRANSICOES[Estado.APROVADA] == {Estado.ENVIADA}
    assert TRANSICOES[Estado.ENVIADA] == set()
    assert TRANSICOES[Estado.ERRO] == {Estado.VALIDADA}
