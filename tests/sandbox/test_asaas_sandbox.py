import os
from dataclasses import replace
from datetime import date, timedelta

import pytest

from boletos.config import URL_SANDBOX_ASAAS
from boletos.gateway.asaas import AsaasGateway
from boletos.models import Cliente, chave_idem

pytestmark = pytest.mark.sandbox

CHAVE = os.environ.get("ASAAS_API_KEY")


@pytest.mark.skipif(not CHAVE, reason="defina ASAAS_API_KEY do sandbox para rodar")
def test_fluxo_real_cria_cliente_emite_e_busca_pela_referencia(fazer_cobranca):
    gw = AsaasGateway(CHAVE, os.environ.get("ASAAS_BASE_URL") or URL_SANDBOX_ASAAS)
    venc = (date.today() + timedelta(days=10)).isoformat()
    ref = chave_idem("11144477735", "2026-11", 1000, venc) + "-teste"
    id_cliente = gw.criar_cliente(Cliente("Cliente Teste Sandbox", "11144477735", "teste@exemplo.test"))
    cobranca = replace(
        fazer_cobranca(),
        id_cliente_gw=id_cliente,
        chave_idem=ref,
        valor_cent=1000,
        vencimento=venc,
        descricao="Boleto de teste (sandbox)",
    )
    emissao = gw.emitir(cobranca)
    assert emissao.link.startswith("https://")
    achada = gw.buscar_por_referencia(ref)
    assert achada is not None and achada.id_gw == emissao.id_gw
