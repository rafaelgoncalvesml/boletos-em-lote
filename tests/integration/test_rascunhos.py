import email
from dataclasses import replace
from email import policy

import pytest

from boletos.lote import gerar_rascunhos
from boletos.mail.composer import ErroRedator
from boletos.models import Estado
from tests.helpers import RedatorFalso

pytestmark = pytest.mark.integration


def _ler(caminho):
    return email.message_from_bytes(caminho.read_bytes(), policy=policy.default)


def test_rn24_rascunho_vira_arquivo_eml_e_registro_no_banco(banco, cfg, lote_emitido):
    lote = lote_emitido(2)
    res = gerar_rascunhos(banco, lote, cfg, RedatorFalso())
    assert (res.gerados, res.pelo_claude, res.modelo_fixo, res.erros) == (2, 2, 0, 0)
    assert banco.contar_por_estado(lote) == {"rascunho": 2}
    c = banco.listar(lote)[0]
    arq = cfg.rascunhos_dir / str(lote) / f"{c.id:05d}.eml"
    msg = _ler(arq)
    assert msg["To"] == c.cliente_email and msg["From"] == cfg.smtp_from
    assert msg["Subject"] == "Boleto de 11/2026, vencimento em 15/12"
    corpo = msg.get_content()
    assert "Olá, Mariana!" in corpo and "R$ 1.250,00" in corpo and "15/12/2026" in corpo
    assert c.link_boleto in corpo
    envio = banco.obter_envio(c.id)
    assert envio["origem_texto"] == "claude" and envio["caminho_rascunho"] == str(arq)


def test_sem_redator_usa_modelo_fixo_sem_evento_de_fallback(banco, cfg, lote_emitido):
    lote = lote_emitido(3)
    res = gerar_rascunhos(banco, lote, cfg, None)
    assert (res.gerados, res.pelo_claude, res.modelo_fixo) == (3, 0, 3)
    tipos = [e["tipo"] for e in banco.eventos(lote)]
    assert "chamada_claude" not in tipos and "fallback_modelo" not in tipos


def test_rn21_claude_que_falha_nao_para_o_lote(banco, cfg, lote_emitido):
    lote = lote_emitido(3)
    res = gerar_rascunhos(banco, lote, cfg, RedatorFalso(erro=ErroRedator("resposta fora do formato")))
    assert (res.gerados, res.modelo_fixo, res.erros) == (3, 3, 0)
    assert banco.contar_por_estado(lote) == {"rascunho": 3}
    fallbacks = [e for e in banco.eventos(lote) if e["tipo"] == "fallback_modelo"]
    assert len(fallbacks) == 3 and all(e["cobranca_id"] for e in fallbacks)
    assert banco.obter_envio(banco.listar(lote)[0].id)["origem_texto"] == "modelo_fixo"


def test_rn22_teto_diario_de_chamadas_ao_claude(banco, cfg, lote_emitido):
    lote = lote_emitido(5)
    redator = RedatorFalso()
    res = gerar_rascunhos(banco, lote, replace(cfg, max_claude_calls_dia=2), redator)
    assert len(redator.chamadas) == 2
    assert (res.pelo_claude, res.modelo_fixo) == (2, 3)
    eventos = banco.eventos(lote)
    assert sum(e["tipo"] == "chamada_claude" for e in eventos) == 2
    assert sum(e["tipo"] == "fallback_modelo" and e["cobranca_id"] is None for e in eventos) == 1


def test_so_cobrancas_emitidas_viram_rascunho(banco, cfg, lote_emitido):
    lote = lote_emitido(2)
    primeira = banco.listar(lote)[0]
    banco.transicionar(primeira.id, Estado.ERRO, etapa_falha="emitir", detalhe="x")
    res = gerar_rascunhos(banco, lote, cfg, None)
    assert res.gerados == 1 and banco.obter(primeira.id).estado == Estado.ERRO


def test_rn31_segredos_nao_aparecem_no_rascunho(banco, cfg, lote_emitido):
    cfg_s = replace(cfg, anthropic_api_key="sk-ant-segredo-xyz", asaas_api_key="chave-asaas-xyz")
    lote = lote_emitido(2)
    gerar_rascunhos(banco, lote, cfg_s, RedatorFalso())
    for arq in (cfg.rascunhos_dir / str(lote)).glob("*.eml"):
        bruto = arq.read_bytes()
        assert b"sk-ant-segredo-xyz" not in bruto and b"chave-asaas-xyz" not in bruto


def test_nome_ou_email_hostil_nao_injeta_cabecalho_e_nao_para_o_lote(banco, cfg, fazer_linha, lote_emitido):
    linhas = [
        fazer_linha(1, nome="Ana\r\nBcc: alguem@exemplo.test"),
        fazer_linha(2, email="b@exemplo.test\nBcc: alguem@exemplo.test"),
        fazer_linha(3),
    ]
    lote = lote_emitido(linhas=linhas)
    res = gerar_rascunhos(banco, lote, cfg, None)
    assert (res.gerados, res.erros) == (2, 1)
    c1, c2, _ = banco.listar(lote)
    assert _ler(cfg.rascunhos_dir / str(lote) / f"{c1.id:05d}.eml")["Bcc"] is None
    assert banco.obter(c2.id).estado == Estado.ERRO and banco.obter(c2.id).etapa_falha == "rascunho"
