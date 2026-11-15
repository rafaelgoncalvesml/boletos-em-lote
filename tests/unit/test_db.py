from datetime import UTC, datetime

import pytest

from boletos.erros import BancoIndisponivel, TransicaoInvalida
from boletos.models import Estado, Rejeicao, chave_da_linha
from boletos.store.db import Banco


def test_abre_migra_e_reabre_sem_erro(tmp_path):
    caminho = tmp_path / "x.db"
    Banco.abrir(caminho).close()
    b = Banco.abrir(caminho)
    assert b.con.execute("PRAGMA user_version").fetchone()[0] == 1
    tabelas = {r[0] for r in b.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"lotes", "cobrancas", "rejeicoes", "envios", "eventos"} <= tabelas
    b.close()


def test_banco_ilegivel_ou_diretorio_aborta_com_erro_claro(tmp_path):
    lixo = tmp_path / "lixo.db"
    lixo.write_bytes(b"isto nao e um banco sqlite" * 50)
    with pytest.raises(BancoIndisponivel):
        Banco.abrir(lixo)
    with pytest.raises(BancoIndisponivel):
        Banco.abrir(tmp_path)  # um diretório


def test_rn09_chave_unica(banco, lote_com, fazer_linha):
    linha = fazer_linha(1)
    lote = lote_com([linha])
    assert banco.buscar_por_chave(chave_da_linha(linha)).lote_id == lote
    with pytest.raises(Exception, match="UNIQUE"):
        banco.inserir_cobranca(lote, linha, chave_da_linha(linha))


def test_inserir_grava_estado_validada_e_evento(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    c = banco.listar(lote)[0]
    assert c.estado == Estado.VALIDADA and c.valor_cent == 125000 and c.vencimento == "2026-12-15"
    assert [e["tipo"] for e in banco.eventos(lote)] == ["importada"]


def test_texto_hostil_e_gravado_como_dado(banco, lote_com, fazer_linha):
    nome = "x'); DROP TABLE cobrancas;--"
    lote = lote_com([fazer_linha(1, nome=nome)])
    assert banco.listar(lote)[0].cliente_nome == nome


def test_rn29_transicao_valida_grava_evento(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    c = banco.listar(lote)[0]
    novo = banco.transicionar(
        c.id, Estado.EMITIDA, id_cobranca_gw="pay_1", link_boleto="https://x.test/1", detalhe="ok"
    )
    assert novo.estado == Estado.EMITIDA and novo.id_cobranca_gw == "pay_1"
    ultimo = banco.eventos(lote)[-1]
    assert (ultimo["estado_antes"], ultimo["estado_depois"], ultimo["detalhe"]) == ("validada", "emitida", "ok")


def test_transicao_proibida_e_recusada(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    c = banco.listar(lote)[0]
    with pytest.raises(TransicaoInvalida):
        banco.transicionar(c.id, Estado.ENVIADA)
    assert banco.obter(c.id).estado == Estado.VALIDADA


def test_erro_exige_etapa_e_voltar_a_validada_limpa_a_etapa(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    c = banco.listar(lote)[0]
    with pytest.raises(ValueError):
        banco.transicionar(c.id, Estado.ERRO)
    e = banco.transicionar(c.id, Estado.ERRO, etapa_falha="emitir", detalhe="recusado")
    assert e.etapa_falha == "emitir" and banco.motivo_erro(c.id) == "recusado"
    assert banco.transicionar(c.id, Estado.VALIDADA).etapa_falha is None


def test_campo_fora_da_lista_e_recusado(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    c = banco.listar(lote)[0]
    with pytest.raises(ValueError):
        banco.transicionar(c.id, Estado.EMITIDA, estado="enviada")


def test_rn13_id_cliente_por_documento(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1, competencia="2026-10"), fazer_linha(1, competencia="2026-11")])
    primeira = banco.listar(lote)[0]
    assert banco.id_cliente_por_doc(primeira.cliente_doc) is None
    banco.definir_cliente_gw(primeira.id, "cus_9")
    assert banco.id_cliente_por_doc(primeira.cliente_doc) == "cus_9"


def test_contagem_por_estado_e_busca_por_doc_competencia(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1), fazer_linha(2)])
    assert banco.contar_por_estado(lote) == {"validada": 2}
    assert len(banco.buscar_por_doc_competencia(fazer_linha(1).documento, "2026-11")) == 1


def test_lote_pausado_segue_o_ultimo_evento(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    assert not banco.lote_pausado(lote)
    banco.registrar_evento(lote, "lote_pausado", "5 falhas seguidas")
    assert banco.lote_pausado(lote)
    banco.registrar_evento(lote, "lote_retomado")
    assert not banco.lote_pausado(lote)


def test_rn22_chamadas_do_claude_contam_so_o_dia_de_hoje(tmp_path):
    agora = {"t": datetime(2026, 11, 15, 10, 0, tzinfo=UTC)}
    b = Banco.abrir(tmp_path / "r.db", relogio=lambda: agora["t"])
    lote = b.criar_lote("a.csv", "h" * 64, 0, 0)
    b.registrar_evento(lote, "chamada_claude")
    b.registrar_evento(lote, "chamada_claude")
    assert b.chamadas_claude_hoje() == 2
    agora["t"] = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
    assert b.chamadas_claude_hoje() == 0
    b.close()


def test_rejeicoes_ficam_guardadas(banco):
    lote = banco.criar_lote("a.csv", "h" * 64, 3, 1)
    banco.inserir_rejeicao(lote, Rejeicao(4, "documento", "dígitos não conferem"))
    assert banco.rejeicoes(lote) == [Rejeicao(4, "documento", "dígitos não conferem")]


def test_envios_ciclo_completo(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1)])
    c = banco.listar(lote)[0]
    banco.salvar_envio(c.id, "rascunhos/1/00001.eml", "Boleto de 11/2026, vencimento em 15/12", "claude")
    banco.marcar_aprovado(c.id)
    banco.registrar_erro_envio(c.id, "conexão recusada")
    assert banco.obter_envio(c.id)["erro"] == "conexão recusada"
    banco.marcar_enviado(c.id)
    envio = banco.obter_envio(c.id)
    assert envio["erro"] is None and envio["enviado_em"] and envio["aprovado_em"]
