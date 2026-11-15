import csv
import io

from boletos.models import Estado, Rejeicao
from boletos.reports import em_csv, em_markdown, montar


def _lote_misto(banco, lote_com, fazer_linha):
    lote = lote_com([fazer_linha(1), fazer_linha(2, valor_cent=50000), fazer_linha(3)])
    a, b, c = banco.listar(lote)
    banco.transicionar(a.id, Estado.EMITIDA, id_cobranca_gw="p1", link_boleto="https://x.test/1")
    banco.transicionar(b.id, Estado.EMITIDA, id_cobranca_gw="p2", link_boleto="https://x.test/2")
    banco.transicionar(c.id, Estado.ERRO, etapa_falha="emitir", detalhe="dados recusados pelo provedor (400)")
    banco.inserir_rejeicao(lote, Rejeicao(9, "documento", "dígitos não conferem"))
    banco.registrar_evento(lote, "aviso_competencia_repetida", "linha 4: possível duplicidade", cobranca_id=a.id)
    return lote, c


def test_rn32_resumo_conta_estados_valor_rejeicoes_erros_e_avisos(banco, lote_com, fazer_linha):
    lote, c = _lote_misto(banco, lote_com, fazer_linha)
    r = montar(banco, lote)
    assert r.por_estado == {"emitida": 2, "erro": 1}
    assert r.valor_emitido_cent == 175000
    assert r.rejeicoes == [Rejeicao(9, "documento", "dígitos não conferem")]
    assert r.erros == [(c.id, "emitir", "dados recusados pelo provedor (400)")]
    assert r.avisos == ["linha 4: possível duplicidade"]


def test_markdown_tem_secoes_e_nao_vaza_dado_pessoal(banco, lote_com, fazer_linha):
    lote, _ = _lote_misto(banco, lote_com, fazer_linha)
    texto = em_markdown(montar(banco, lote))
    assert "emitida" in texto and "R$ 1.750,00" in texto and "dígitos não conferem" in texto
    assert "exemplo.test" not in texto and "00000000001" not in texto


def test_csv_e_parseavel_e_traz_o_total(banco, lote_com, fazer_linha):
    lote, _ = _lote_misto(banco, lote_com, fazer_linha)
    linhas = list(csv.reader(io.StringIO(em_csv(montar(banco, lote)))))
    assert linhas[0] == ["secao", "chave", "valor", "detalhe"]
    assert ["total", "valor_emitido_cent", "175000", ""] in linhas
    assert ["estado", "emitida", "2", ""] in linhas
