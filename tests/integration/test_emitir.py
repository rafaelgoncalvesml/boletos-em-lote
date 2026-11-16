from dataclasses import replace

import pytest

from boletos.erros import CredencialRecusada, EntradaRecusada, LotePausado
from boletos.gateway.base import ErroTemporario
from boletos.gateway.fake import FakeGateway
from boletos.lote import emitir, reprocessar
from boletos.models import Estado

pytestmark = pytest.mark.integration


class Relogio:
    def __init__(self):
        self.esperas = []

    def __call__(self, segundos):
        self.esperas.append(segundos)


@pytest.fixture
def dormir():
    return Relogio()


def _linhas(fazer_linha, n):
    return [fazer_linha(i) for i in range(1, n + 1)]


def test_emite_todas_e_pausa_entre_requisicoes(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 3))
    res = emitir(banco, FakeGateway(), lote, replace(cfg, pausa_entre_req_ms=300), dormir=dormir)
    assert (res.emitidas, res.erros, res.pausado) == (3, 0, False)
    assert banco.contar_por_estado(lote) == {"emitida": 3}
    assert dormir.esperas == [0.3, 0.3]
    c = banco.listar(lote)[0]
    assert c.id_cobranca_gw and c.link_boleto and c.linha_digitavel and c.id_cliente_gw


def test_rn11_interrupcao_entre_o_post_e_o_commit_nao_duplica_o_boleto(
    banco, cfg, fazer_linha, lote_com, dormir, monkeypatch
):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway()
    original = banco.transicionar

    def cai_uma_vez(*args, **kwargs):
        monkeypatch.setattr(banco, "transicionar", original)
        raise KeyboardInterrupt

    # o gateway já criou o boleto quando o processo morre, antes de gravar a emissão
    monkeypatch.setattr(banco, "transicionar", cai_uma_vez)
    with pytest.raises(KeyboardInterrupt):
        emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.total_emitido == 1 and banco.contar_por_estado(lote) == {"validada": 1}

    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert res.emitidas == 1 and gw.total_emitido == 1
    assert banco.listar(lote)[0].id_cobranca_gw == "pay_fake_00001"


def test_rn11_reprocessar_depois_de_esgotar_as_tentativas_nao_duplica_o_boleto(
    banco, cfg, fazer_linha, lote_com, dormir
):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway(["temp", "temp", "temp", "cair_apos_criar"])
    emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.total_emitido == 1
    for c in banco.listar(lote):
        if c.estado == Estado.ERRO:
            reprocessar(banco, c.id)
    emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.total_emitido == 1
    assert banco.contar_por_estado(lote) == {"emitida": 1}


def test_rn11_consulta_final_falhando_mantem_o_erro_da_emissao(banco, cfg, fazer_linha, lote_com, dormir):
    class BuscaFora(FakeGateway):
        def buscar_por_referencia(self, ref):
            if self.chamadas_emitir == 4:
                raise ErroTemporario("busca fora do ar")
            return super().buscar_por_referencia(ref)

    lote = lote_com(_linhas(fazer_linha, 1))
    gw = BuscaFora(["temp"] * 4)
    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert res.erros == 1 and gw.chamadas_emitir == 4
    assert "timeout simulado" in banco.motivo_erro(banco.listar(lote)[0].id)


def test_rn12_so_validadas_sao_emitidas(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 2))
    primeira = banco.listar(lote)[0]
    banco.transicionar(primeira.id, Estado.ERRO, etapa_falha="emitir", detalhe="x")
    gw = FakeGateway()
    emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.total_emitido == 1 and banco.obter(primeira.id).estado == Estado.ERRO


def test_rn13_cliente_e_criado_uma_vez_por_documento(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com([fazer_linha(1, competencia="2026-10"), fazer_linha(1, competencia="2026-11"), fazer_linha(2)])
    gw = FakeGateway()
    emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.chamadas_criar_cliente == 2
    ids = {c.cliente_doc: c.id_cliente_gw for c in banco.listar(lote)}
    assert len(set(ids.values())) == 2


def test_rn16_falhas_na_3a_e_na_7a_nao_param_o_lote(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 10))
    gw = FakeGateway([None, None, "perm", None, None, None, "perm"])
    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert (res.emitidas, res.erros, res.pausado) == (8, 2, False)
    erros = [c for c in banco.listar(lote) if c.estado == Estado.ERRO]
    assert [c.id for c in erros] == [3, 7]
    assert all(c.etapa_falha == "emitir" and "recusados" in banco.motivo_erro(c.id) for c in erros)


def test_rn15_timeout_repete_com_espera_crescente_e_consulta_antes(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway(["temp", "temp"])
    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert res.emitidas == 1 and gw.total_emitido == 1
    assert dormir.esperas == [1, 3] and gw.chamadas_buscar == 3


def test_rn15_esgota_as_tentativas_e_marca_erro(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway(["temp"] * 4)
    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert res.erros == 1 and gw.chamadas_emitir == 4
    assert dormir.esperas == [1, 3, 9]
    assert banco.listar(lote)[0].etapa_falha == "emitir"


def test_rn15_erro_4xx_nao_repete(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway(["perm"])
    emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.chamadas_emitir == 1 and dormir.esperas == []


def test_rn11_gateway_cai_depois_de_criar_e_a_busca_evita_duplicata(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway(["cair_apos_criar"])
    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert res.emitidas == 1
    assert gw.total_emitido == 1 and gw.chamadas_emitir == 1
    assert banco.listar(lote)[0].id_cobranca_gw == "pay_fake_00001"


def test_rn16_cinco_falhas_seguidas_pausam_e_retomar_conclui(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 8))
    gw = FakeGateway(["perm"] * 5)
    res = emitir(banco, gw, lote, cfg, dormir=dormir)
    assert res.pausado and res.erros == 5 and res.emitidas == 0
    assert banco.contar_por_estado(lote) == {"erro": 5, "validada": 3}
    assert banco.lote_pausado(lote)
    with pytest.raises(LotePausado):
        emitir(banco, gw, lote, cfg, dormir=dormir)
    res2 = emitir(banco, gw, lote, cfg, retomar=True, dormir=dormir)
    assert res2.emitidas == 3 and not res2.pausado
    assert not banco.lote_pausado(lote)
    assert banco.contar_por_estado(lote) == {"erro": 5, "emitida": 3}


def test_rn17_credencial_recusada_para_na_hora_sem_marcar_erro(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 3))
    gw = FakeGateway(["credencial"])
    with pytest.raises(CredencialRecusada):
        emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.chamadas_emitir == 1 and dormir.esperas == []
    assert banco.contar_por_estado(lote) == {"validada": 3}
    assert "credencial_recusada" in [e["tipo"] for e in banco.eventos(lote)]


def test_reprocessar_volta_a_validada_e_so_erro_pode(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway(["perm"])
    emitir(banco, gw, lote, cfg, dormir=dormir)
    cid = banco.listar(lote)[0].id
    assert reprocessar(banco, cid).estado == Estado.VALIDADA
    assert emitir(banco, gw, lote, cfg, dormir=dormir).emitidas == 1
    with pytest.raises(EntradaRecusada):
        reprocessar(banco, cid)


def test_reprocessar_depois_de_emitida_nao_emite_de_novo(banco, cfg, fazer_linha, lote_com, dormir):
    lote = lote_com(_linhas(fazer_linha, 1))
    gw = FakeGateway()
    emitir(banco, gw, lote, cfg, dormir=dormir)
    cid = banco.listar(lote)[0].id
    banco.transicionar(cid, Estado.ERRO, etapa_falha="rascunho", detalhe="disco cheio")
    reprocessar(banco, cid)
    emitir(banco, gw, lote, cfg, dormir=dormir)
    assert gw.total_emitido == 1 and banco.obter(cid).estado == Estado.EMITIDA
