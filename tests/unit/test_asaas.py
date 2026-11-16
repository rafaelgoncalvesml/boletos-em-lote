import json

import httpx
import pytest

from boletos.gateway.asaas import AsaasGateway
from boletos.gateway.base import ErroCredencial, ErroPermanente, ErroTemporario
from boletos.models import Cliente

CHAVE = "chave-sandbox-secreta"
PAGAMENTO = {
    "id": "pay_1",
    "bankSlipUrl": "https://sandbox.asaas.test/b/1",
    "invoiceUrl": "https://sandbox.asaas.test/i/1",
}


def _gw(handler):
    return AsaasGateway(CHAVE, "https://api.exemplo.test/v3", transport=httpx.MockTransport(handler))


def test_criar_cliente_envia_dados_e_desliga_notificacao():
    vistos = {}

    def handler(req):
        vistos["caminho"] = req.url.path
        vistos["chave"] = req.headers.get("access_token")
        vistos["corpo"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "cus_1"})

    id_ = _gw(handler).criar_cliente(Cliente("Ana", "11144477735", "ana@exemplo.test"))
    assert id_ == "cus_1"
    assert vistos["caminho"] == "/v3/customers" and vistos["chave"] == CHAVE
    assert vistos["corpo"] == {
        "name": "Ana",
        "cpfCnpj": "11144477735",
        "email": "ana@exemplo.test",
        "notificationDisabled": True,
    }


def test_emitir_cria_boleto_com_referencia_externa_e_busca_linha_digitavel(fazer_cobranca):
    corpos = []

    def handler(req):
        if req.method == "POST":
            corpos.append(json.loads(req.content))
            return httpx.Response(200, json=PAGAMENTO)
        assert req.url.path.endswith("/payments/pay_1/identificationField")
        return httpx.Response(200, json={"identificationField": "11111.22222 33333.444444"})

    c = fazer_cobranca(chave_idem="k" * 64, valor_cent=125050, vencimento="2026-12-15", descricao="Mensalidade")
    e = _gw(handler).emitir(c)
    assert (e.id_gw, e.link, e.linha_digitavel) == ("pay_1", PAGAMENTO["bankSlipUrl"], "11111.22222 33333.444444")
    assert corpos[0] == {
        "customer": "cus_1",
        "billingType": "BOLETO",
        "value": 1250.5,
        "dueDate": "2026-12-15",
        "description": "Mensalidade",
        "externalReference": "k" * 64,
    }


def test_emitir_sem_descricao_usa_a_competencia(fazer_cobranca):
    corpos = []

    def handler(req):
        if req.method == "POST":
            corpos.append(json.loads(req.content))
            return httpx.Response(200, json=PAGAMENTO)
        return httpx.Response(200, json={"identificationField": "x"})

    _gw(handler).emitir(fazer_cobranca(descricao=""))
    assert corpos[0]["description"] == "Competência 11/2026"


def test_buscar_por_referencia_encontra_e_nao_encontra():
    def handler(req):
        if req.url.path.endswith("/identificationField"):
            return httpx.Response(200, json={"identificationField": "linha"})
        achou = req.url.params["externalReference"] == "existe"
        return httpx.Response(200, json={"data": [PAGAMENTO] if achou else []})

    gw = _gw(handler)
    assert gw.buscar_por_referencia("existe").id_gw == "pay_1"
    assert gw.buscar_por_referencia("nao-existe") is None


@pytest.mark.parametrize(
    "status,erro",
    [
        (401, ErroCredencial),
        (403, ErroCredencial),
        (429, ErroTemporario),
        (500, ErroTemporario),
        (503, ErroTemporario),
        (400, ErroPermanente),
        (404, ErroPermanente),
    ],
)
def test_rn15_rn17_mapeamento_de_status_para_erro(status, erro, fazer_cobranca):
    gw = _gw(lambda req: httpx.Response(status, json={"errors": [{"description": "CPF/CNPJ inválido"}]}))
    with pytest.raises(erro) as e:
        gw.emitir(fazer_cobranca())
    assert CHAVE not in str(e.value)


def test_mensagem_do_provedor_vai_para_o_erro_permanente(fazer_cobranca):
    gw = _gw(lambda req: httpx.Response(400, json={"errors": [{"description": "CPF/CNPJ inválido"}]}))
    with pytest.raises(ErroPermanente, match="CPF/CNPJ inválido"):
        gw.emitir(fazer_cobranca())


def test_timeout_e_falha_de_rede_sao_temporarios(fazer_cobranca):
    def estoura(req):
        raise httpx.ReadTimeout("lento", request=req)

    def cai(req):
        raise httpx.ConnectError("sem rede", request=req)

    for handler in (estoura, cai):
        with pytest.raises(ErroTemporario) as e:
            _gw(handler).emitir(fazer_cobranca())
        assert CHAVE not in str(e.value)


def test_boleto_sem_link_e_erro_temporario(fazer_cobranca):
    def handler(req):
        return httpx.Response(200, json={"id": "pay_9"})

    with pytest.raises(ErroTemporario, match="link"):
        _gw(handler).emitir(fazer_cobranca())


@pytest.mark.parametrize(
    "resposta",
    [
        httpx.Response(200, json={"sem_id": True}),
        httpx.Response(200, json=["inesperado"]),
        httpx.Response(200, text="<html>manutenção</html>"),
    ],
)
def test_resposta_2xx_malformada_e_erro_temporario_sem_o_corpo(resposta, fazer_cobranca):
    gw = _gw(lambda req: resposta)
    with pytest.raises(ErroTemporario) as e:
        gw.criar_cliente(Cliente("Ana", "11144477735", "ana@exemplo.test"))
    assert "manutenção" not in str(e.value)
    with pytest.raises(ErroTemporario):
        gw.emitir(fazer_cobranca())


def test_pagamento_2xx_sem_id_e_erro_temporario(fazer_cobranca):
    gw = _gw(lambda req: httpx.Response(200, json={"bankSlipUrl": "https://sandbox.asaas.test/b/1"}))
    with pytest.raises(ErroTemporario):
        gw.emitir(fazer_cobranca())
    with pytest.raises(ErroTemporario):
        _gw(lambda req: httpx.Response(200, json={"data": [{"bankSlipUrl": "x"}]})).buscar_por_referencia("k")
