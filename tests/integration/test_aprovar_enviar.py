import pytest

from boletos.erros import EntradaRecusada
from boletos.lote import aprovar, enviar, gerar_rascunhos
from boletos.models import Estado
from tests.helpers import SenderFalso

pytestmark = pytest.mark.integration


@pytest.fixture
def rascunhos(banco, cfg, lote_emitido):
    def _fazer(n=3):
        lote = lote_emitido(n)
        gerar_rascunhos(banco, lote, cfg, None)
        return lote

    return _fazer


def test_rn25_aprovar_lote_leva_todos_os_rascunhos_para_aprovada(banco, rascunhos):
    lote = rascunhos(3)
    assert aprovar(banco, lote_id=lote) == 3
    assert banco.contar_por_estado(lote) == {"aprovada": 3}
    assert all(banco.obter_envio(c.id)["aprovado_em"] for c in banco.listar(lote))
    assert aprovar(banco, lote_id=lote) == 0  # nada mais em rascunho


def test_rn25_aprovar_uma_cobranca(banco, rascunhos):
    lote = rascunhos(3)
    primeira = banco.listar(lote)[0]
    assert aprovar(banco, cobranca_id=primeira.id) == 1
    assert banco.contar_por_estado(lote) == {"aprovada": 1, "rascunho": 2}


def test_aprovar_exige_um_alvo_e_so_rascunho_pode_ser_aprovado(banco, rascunhos):
    lote = rascunhos(2)
    primeira = banco.listar(lote)[0]
    with pytest.raises(EntradaRecusada):
        aprovar(banco)
    with pytest.raises(EntradaRecusada):
        aprovar(banco, lote_id=lote, cobranca_id=primeira.id)
    with pytest.raises(EntradaRecusada, match="não existe"):
        aprovar(banco, cobranca_id=9999)
    aprovar(banco, cobranca_id=primeira.id)
    with pytest.raises(EntradaRecusada, match="aprovada"):
        aprovar(banco, cobranca_id=primeira.id)


def test_rn26_enviar_sem_confirmar_lista_e_nao_envia_nada(banco, rascunhos):
    lote = rascunhos(3)
    aprovar(banco, lote_id=lote)
    sender = SenderFalso()
    res = enviar(banco, lote, sender, confirmar=False)
    assert len(res.previstas) == 3 and not res.confirmado and res.enviadas == 0
    assert sender.enviados == []
    assert banco.contar_por_estado(lote) == {"aprovada": 3}
    assert enviar(banco, lote, None).previstas == res.previstas  # sem confirmar nem precisa de sender


def test_enviar_confirmado_manda_so_as_aprovadas(banco, rascunhos):
    lote = rascunhos(3)
    primeira = banco.listar(lote)[0]
    aprovar(banco, cobranca_id=primeira.id)
    sender = SenderFalso()
    res = enviar(banco, lote, sender, confirmar=True)
    assert (res.enviadas, res.falhas) == (1, 0) and len(sender.enviados) == 1
    assert banco.obter(primeira.id).estado == Estado.ENVIADA
    assert banco.contar_por_estado(lote) == {"enviada": 1, "rascunho": 2}
    assert banco.obter_envio(primeira.id)["enviado_em"]


def test_nada_sai_sem_aprovacao_mesmo_com_confirmar(banco, rascunhos):
    lote = rascunhos(3)
    sender = SenderFalso()
    res = enviar(banco, lote, sender, confirmar=True)
    assert res.enviadas == 0 and sender.enviados == []


def test_rn27_reenvio_so_com_flag_e_grava_evento_proprio(banco, rascunhos):
    lote = rascunhos(2)
    aprovar(banco, lote_id=lote)
    sender = SenderFalso()
    enviar(banco, lote, sender, confirmar=True)
    assert enviar(banco, lote, sender, confirmar=True).enviadas == 0
    res = enviar(banco, lote, sender, confirmar=True, reenviar=True)
    assert res.enviadas == 2 and res.reenvios == 2 and len(sender.enviados) == 4
    assert banco.contar_por_estado(lote) == {"enviada": 2}
    assert sum(e["tipo"] == "reenvio" for e in banco.eventos(lote)) == 2


def test_rn28_falha_de_smtp_mantem_aprovada_e_o_comando_pode_ser_repetido(banco, rascunhos):
    lote = rascunhos(2)
    aprovar(banco, lote_id=lote)
    sender = SenderFalso(falhas=1)
    res = enviar(banco, lote, sender, confirmar=True)
    assert (res.enviadas, res.falhas) == (1, 1)
    primeira, segunda = banco.listar(lote)
    assert primeira.estado == Estado.APROVADA and segunda.estado == Estado.ENVIADA
    assert "fora do ar" in banco.obter_envio(primeira.id)["erro"]
    assert "erro_envio" in [e["tipo"] for e in banco.eventos(lote)]
    res2 = enviar(banco, lote, sender, confirmar=True)
    assert res2.enviadas == 1 and banco.obter(primeira.id).estado == Estado.ENVIADA
    assert banco.obter_envio(primeira.id)["erro"] is None
