import pytest

from boletos.gateway.base import ErroCredencial, ErroPermanente, ErroTemporario
from boletos.gateway.fake import FakeGateway
from boletos.models import Cliente


def test_emite_e_busca_pela_referencia(fazer_cobranca):
    gw = FakeGateway()
    c = fazer_cobranca(chave_idem="k" * 64)
    emissao = gw.emitir(c)
    assert emissao.link.startswith("https://") and ".test/" in emissao.link
    assert gw.buscar_por_referencia("k" * 64) == emissao
    assert gw.buscar_por_referencia("outra") is None
    assert gw.total_emitido == 1


@pytest.mark.parametrize(
    "passo,erro", [("temp", ErroTemporario), ("perm", ErroPermanente), ("credencial", ErroCredencial)]
)
def test_roteiro_simula_falhas(fazer_cobranca, passo, erro):
    gw = FakeGateway([passo])
    with pytest.raises(erro):
        gw.emitir(fazer_cobranca())
    assert gw.total_emitido == 0
    gw.emitir(fazer_cobranca())  # roteiro acabou, volta ao normal
    assert gw.total_emitido == 1


def test_credencial_e_um_erro_permanente():
    assert issubclass(ErroCredencial, ErroPermanente)


def test_cair_apos_criar_cria_e_levanta(fazer_cobranca):
    gw = FakeGateway(["cair_apos_criar"])
    c = fazer_cobranca(chave_idem="z" * 64)
    with pytest.raises(ErroTemporario):
        gw.emitir(c)
    assert gw.total_emitido == 1
    assert gw.buscar_por_referencia("z" * 64) is not None


def test_cria_cliente_com_id_novo_a_cada_chamada():
    gw = FakeGateway()
    a = gw.criar_cliente(Cliente("Ana", "11144477735", "a@exemplo.test"))
    b = gw.criar_cliente(Cliente("Bia", "52998224725", "b@exemplo.test"))
    assert a != b and gw.chamadas_criar_cliente == 2
