import pytest

from boletos.mail.guard import conferir_final, conferir_partes

VALOR = "R$ 1.250,00"
VENC = "15/12/2026"
LINK = "https://sandbox.exemplo.test/boleto/00001"


def _corpo(valor=VALOR, venc=VENC, link=LINK, extra=""):
    return f"Olá, Ana.\n\nSegue a cobrança.\n{extra}\nValor: {valor}\nVencimento: {venc}\nLink do boleto: {link}\n"


def test_rn20_partes_limpas_passam():
    assert conferir_partes("Olá, Ana!", "Segue a cobrança da mensalidade de novembro.").ok


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
