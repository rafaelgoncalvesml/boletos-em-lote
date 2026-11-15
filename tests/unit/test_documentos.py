import pytest

from boletos.validation.documentos import (
    cnpj_valido,
    cpf_valido,
    documento_valido,
    somente_digitos,
)


@pytest.mark.parametrize("doc", ["11144477735", "52998224725"])
def test_rn03_cpf_valido(doc):
    assert cpf_valido(doc) and documento_valido(doc)


@pytest.mark.parametrize("doc", ["11144477736", "11111111111", "1114447773", "", "abc44477735"])
def test_rn03_cpf_invalido(doc):
    assert not cpf_valido(doc) and not documento_valido(doc)


def test_rn03_cnpj_valido():
    assert cnpj_valido("11222333000181") and documento_valido("11222333000181")


@pytest.mark.parametrize("doc", ["11222333000182", "00000000000000", "1122233300018"])
def test_rn03_cnpj_invalido(doc):
    assert not cnpj_valido(doc) and not documento_valido(doc)


def test_somente_digitos_tira_mascara():
    assert somente_digitos("111.444.777-35") == "11144477735"
    assert somente_digitos("11.222.333/0001-81") == "11222333000181"
