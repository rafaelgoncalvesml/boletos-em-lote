import re

import pytest
from typer.testing import CliRunner

from boletos import cli
from boletos.gateway.fake import FakeGateway
from boletos.lote import aprovar, emitir, enviar, gerar_rascunhos, importar
from boletos.mail.composer import RedatorClaude, Texto
from tests.conftest import CNPJ_1, CPF_1, CPF_2
from tests.helpers import ClienteFalso, RedatorFalso, SenderFalso

pytestmark = pytest.mark.integration
runner = CliRunner()


def _importar_tres(banco, cfg, hoje, escrever_csv):
    linhas = [
        f'Ana,{doc},{nome}@exemplo.test,"1.250,00",15/12/2026,2026-11,Mensalidade'
        for nome, doc in (("ana", CPF_1), ("bia", CPF_2), ("cia", CNPJ_1))
    ]
    return importar(banco, escrever_csv(linhas), cfg, hoje).lote_id


def test_lote_completo_com_fake_gateway_chega_a_enviada_so_com_aprovacao(banco, cfg, hoje, escrever_csv):
    lote = _importar_tres(banco, cfg, hoje, escrever_csv)
    emitir(banco, FakeGateway(), lote, cfg, dormir=lambda s: None)
    gerar_rascunhos(banco, lote, cfg, RedatorFalso())
    sender = SenderFalso()
    assert enviar(banco, lote, sender, confirmar=True).enviadas == 0  # nada aprovado, nada sai
    assert aprovar(banco, lote_id=lote) == 3
    res = enviar(banco, lote, sender, confirmar=True)
    assert res.enviadas == 3 and len(sender.enviados) == 3
    assert banco.contar_por_estado(lote) == {"enviada": 3}
    eventos = banco.eventos(lote)
    for c in banco.listar(lote):
        tipos = [e["tipo"] for e in eventos if e["cobranca_id"] == c.id and e["estado_depois"]]
        assert tipos == ["importada", "estado_emitida", "estado_rascunho", "estado_aprovada", "estado_enviada"]


def test_rn21_claude_simulado_devolve_texto_quebrado_e_o_lote_termina(banco, cfg, hoje, escrever_csv):
    lote = _importar_tres(banco, cfg, hoje, escrever_csv)
    emitir(banco, FakeGateway(), lote, cfg, dormir=lambda s: None)
    redator = RedatorClaude(ClienteFalso("isto não é JSON, é só conversa"), "claude-haiku-5-5")
    res = gerar_rascunhos(banco, lote, cfg, redator)
    assert (res.gerados, res.modelo_fixo, res.erros) == (3, 3, 0)
    aprovar(banco, lote_id=lote)
    assert enviar(banco, lote, SenderFalso(), confirmar=True).enviadas == 3
    assert sum(e["tipo"] == "fallback_modelo" for e in banco.eventos(lote)) == 3


def test_rn20_texto_do_claude_que_mexe_no_valor_nunca_chega_ao_rascunho(banco, cfg, hoje, escrever_csv):
    lote = _importar_tres(banco, cfg, hoje, escrever_csv)
    emitir(banco, FakeGateway(), lote, cfg, dormir=lambda s: None)
    malandro = RedatorFalso(
        Texto(saudacao="Olá!", contexto="Por promoção o valor é R$ 1,00 neste link http://golpe.test")
    )
    gerar_rascunhos(banco, lote, cfg, malandro)
    for arq in (cfg.rascunhos_dir / str(lote)).glob("*.eml"):
        texto = arq.read_text(encoding="utf-8")
        assert "R$ 1,00" not in texto and "golpe.test" not in texto and "1.250,00" in texto


def test_reexecutar_lote_inteiro_nao_cria_boleto_nem_cobranca_nova(banco, cfg, hoje, escrever_csv):
    gw = FakeGateway()
    lote = _importar_tres(banco, cfg, hoje, escrever_csv)
    emitir(banco, gw, lote, cfg, dormir=lambda s: None)
    nova = _importar_tres(banco, cfg, hoje, escrever_csv)  # o mesmo arquivo de novo
    emitir(banco, gw, nova, cfg, dormir=lambda s: None)
    assert gw.total_emitido == 3
    assert banco.listar(nova) == []
    assert banco.con.execute("SELECT COUNT(*) FROM cobrancas").fetchone()[0] == 3


def test_fluxo_pela_cli_ate_o_smtp_de_captura_sem_vazar_segredo_nem_documento(
    ambiente, planilha, monkeypatch, servidor_smtp
):
    captura, porta = servidor_smtp
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(porta))
    monkeypatch.setenv("ASAAS_API_KEY", "chave-asaas-teste-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste-123")
    saidas = []

    def rodar(*args, esperado=0):
        r = runner.invoke(cli.app, list(args))
        saidas.append(r.output)
        assert r.exit_code == esperado, r.output
        return r

    rodar("importar", "clientes.csv")
    rodar("emitir", "--lote", "1")
    rodar("rascunhos", "--lote", "1", "--sem-claude")
    rodar("enviar", "--lote", "1", "--confirmar")  # nada aprovado ainda
    assert captura.envelopes == []
    rodar("aprovar", "--lote", "1")
    rodar("enviar", "--lote", "1")  # sem --confirmar
    assert captura.envelopes == []
    rodar("enviar", "--lote", "1", "--confirmar")
    assert len(captura.envelopes) == 20
    rodar("enviar", "--lote", "1", "--confirmar")  # repetir não reenvia
    assert len(captura.envelopes) == 20
    rodar("relatorio", "--lote", "1")

    tudo = "\n".join(saidas)
    arquivos = [p for p in ambiente.rglob("*") if p.is_file() and p.suffix in {".log", ".eml"}]
    arquivos_texto = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in arquivos)
    for segredo in ("chave-asaas-teste-123", "sk-ant-teste-123"):
        assert segredo not in tudo and segredo not in arquivos_texto
    assert not re.search(r"\b\d{11}\b|\b\d{14}\b", tudo + arquivos_texto)
