import pytest

from boletos.mail.guard import conferir_final, conferir_partes

VALOR = "R$ 1.250,00"
VENC = "15/12/2026"
LINK = "https://sandbox.exemplo.test/boleto/00001"


def _corpo(valor=VALOR, venc=VENC, link=LINK, extra=""):
    return f"Olá, Ana.\n\nSegue a cobrança.\n{extra}\nValor: {valor}\nVencimento: {venc}\nLink do boleto: {link}\n"


def test_rn20_partes_limpas_passam():
    assert conferir_partes("Olá, Ana!", "Segue a cobrança da mensalidade.").ok


@pytest.mark.parametrize(
    "contexto",
    [
        "Pague R$ 10,00 hoje.",
        "São 1.250,00 reais.",
        "Veja https://golpe.test agora.",
        "Acesse www.golpe.test.",
        "Vence em 15/12/2026.",
        "Vence em 15/12.",
        "Data 2026-12-15.",
    ],
)
def test_rn20_partes_com_valor_url_ou_data_reprovam(contexto):
    veredito = conferir_partes("Olá!", contexto)
    assert not veredito.ok and veredito.motivo


@pytest.mark.parametrize(
    "contexto",
    [
        "O valor é de 1.500 reais.",
        "Vence em 10 de dezembro de 2026.",
        "Pague pelo Pix na chave pagamentos@golpe.test.",
        "Ligue 11 99999-9999 para pagar.",
        "Faça a transferência para a conta 12345-6 do banco X.",
        "Referente a 11/2026.",
        "Mande um e-mail para cobranca@golpe.test.",
        "Basta fazer um depósito hoje.",
        "Pode quitar por TED.",
        "Use os dados bancários abaixo.",
        "O prazo vai até março.",
        "Tudo certo com o valor em real.",
    ],
)
def test_rn20_partes_com_vocabulario_de_pagamento_digito_ou_arroba_reprovam(contexto):
    veredito = conferir_partes("Olá!", contexto)
    assert not veredito.ok and veredito.motivo


def test_rn20_saudacao_tambem_e_conferida():
    assert not conferir_partes("Olá, Ana! Pague por Pix.", "Segue a cobrança.").ok
    assert not conferir_partes("Olá, Ana 2!", "Segue a cobrança.").ok


def test_rn20_palavra_parecida_nao_reprova():
    assert conferir_partes("Olá, Ana!", "Realmente agradecemos a parceria e a pontualidade de sempre.").ok


def test_rn20_saudacao_e_contexto_amigaveis_sem_dados_passam():
    veredito = conferir_partes(
        "Olá, Mariana, tudo bem?", "Estamos enviando o boleto da mensalidade para você acertar com calma. Obrigado!"
    )
    assert veredito.ok


def test_rn20_final_completo_passa():
    assert conferir_final(_corpo(), valor=VALOR, vencimento=VENC, link=LINK).ok


@pytest.mark.parametrize(
    "corpo,trecho",
    [
        (_corpo(valor="R$ 9,99"), "valor"),
        (_corpo(venc=""), "vencimento"),
        (_corpo(link=""), "link"),
    ],
)
def test_rn20_final_sem_valor_vencimento_ou_link_reprova(corpo, trecho):
    veredito = conferir_final(corpo, valor=VALOR, vencimento=VENC, link=LINK)
    assert not veredito.ok and trecho in veredito.motivo


def test_rn20_final_com_url_extra_reprova():
    corpo = _corpo(extra="Veja também https://golpe.test/x")
    assert not conferir_final(corpo, valor=VALOR, vencimento=VENC, link=LINK).ok


def test_rn20_final_com_outro_valor_em_reais_reprova():
    corpo = _corpo(extra="Taxa extra: R$ 9,99")
    assert not conferir_final(corpo, valor=VALOR, vencimento=VENC, link=LINK).ok
