from __future__ import annotations

import httpx

from boletos.config import URL_SANDBOX_ASAAS
from boletos.formatos import competencia_br
from boletos.gateway.base import ErroCredencial, ErroPermanente, ErroTemporario
from boletos.models import Cliente, Cobranca, Emissao


def _mensagem(resposta: httpx.Response) -> str:
    try:
        return str(resposta.json()["errors"][0]["description"])[:200]
    except (ValueError, KeyError, IndexError, TypeError):
        return "sem detalhe do provedor"


def _id_da_resposta(dados: dict) -> str:
    id_ = dados.get("id")
    if not isinstance(id_, str) or not id_:
        raise ErroTemporario("resposta do provedor sem identificador")
    return id_


class AsaasGateway:
    def __init__(
        self,
        api_key: str,
        base_url: str = URL_SANDBOX_ASAAS,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"access_token": api_key, "User-Agent": "boletos-em-lote/0.1"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _chamar(self, metodo: str, caminho: str, **kwargs) -> dict:
        try:
            resposta = self._http.request(metodo, caminho, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as erro:
            raise ErroTemporario(f"falha de rede ({type(erro).__name__})") from None
        status = resposta.status_code
        if status in (401, 403):
            raise ErroCredencial(f"chave de API recusada pelo provedor ({status})")
        if status == 429 or status >= 500:
            raise ErroTemporario(f"provedor indisponível ou limitando requisições ({status})")
        if status >= 400:
            raise ErroPermanente(f"dados recusados pelo provedor ({status}): {_mensagem(resposta)}")
        try:
            corpo = resposta.json()
        except ValueError:
            raise ErroTemporario("resposta do provedor não é JSON") from None
        if not isinstance(corpo, dict):
            raise ErroTemporario("resposta do provedor com formato inesperado")
        return corpo

    def criar_cliente(self, cliente: Cliente) -> str:
        corpo = {
            "name": cliente.nome,
            "cpfCnpj": cliente.documento,
            "email": cliente.email,
            "notificationDisabled": True,
        }
        return _id_da_resposta(self._chamar("POST", "/customers", json=corpo))

    def emitir(self, cobranca: Cobranca) -> Emissao:
        corpo = {
            "customer": cobranca.id_cliente_gw,
            "billingType": "BOLETO",
            "value": round(cobranca.valor_cent / 100, 2),
            "dueDate": cobranca.vencimento,
            "description": cobranca.descricao or f"Competência {competencia_br(cobranca.competencia)}",
            "externalReference": cobranca.chave_idem,
        }
        return self._emissao(self._chamar("POST", "/payments", json=corpo))

    def buscar_por_referencia(self, ref: str) -> Emissao | None:
        dados = self._chamar("GET", "/payments", params={"externalReference": ref})
        achados = dados.get("data") or []
        return self._emissao(achados[0]) if achados else None

    def _emissao(self, pagamento: dict) -> Emissao:
        link = pagamento.get("bankSlipUrl") or pagamento.get("invoiceUrl")
        if not link:
            raise ErroTemporario("boleto criado, mas o provedor ainda não devolveu o link")
        id_gw = _id_da_resposta(pagamento)
        campo = self._chamar("GET", f"/payments/{id_gw}/identificationField")
        return Emissao(id_gw=id_gw, link=link, linha_digitavel=campo.get("identificationField", ""))
