from datetime import date

import pytest

from boletos.validation.regras import (
    ErroCampo,
    limpar_texto,
    normalizar_cabecalho,
    parse_data,
    parse_documento,
    parse_valor,
    validar_competencia,
    validar_email,
    validar_linha,
    validar_vencimento,
)

HOJE = date(2026, 11, 15)
MAXIMO = 5_000_000


@pytest.mark.parametrize(
    "texto,esperado",
    [("1.250,00", 125000), ("1250.5", 125050), ("1250,5", 125050), ("0,01", 1), ("50.000,00", 5_000_000)],
)
def test_rn04_valor_valido(texto, esperado):
    assert parse_valor(texto, MAXIMO) == esperado


@pytest.mark.parametrize(
    "texto", ["10,999", "1.250", "1,250.00", "1.2.50,00", "0", "0,00", "-5", "abc", "", "50.000,01"]
)
def test_rn04_valor_recusado_nunca_arredondado_nem_relido(texto):
    with pytest.raises(ErroCampo) as erro:
        parse_valor(texto, MAXIMO)
    assert erro.value.coluna == "valor"


def test_rn04_tres_casas_diz_o_motivo():
    with pytest.raises(ErroCampo, match="casas"):
        parse_valor("10,999", MAXIMO)


@pytest.mark.parametrize("texto", ["15/12/2026", "2026-12-15", "1/12/2026"])
def test_rn02_datas_nos_dois_formatos(texto):
    assert isinstance(parse_data(texto), date)


@pytest.mark.parametrize("texto", ["31/02/2027", "2026-02-30", "15-12-2026", "", "amanhã"])
def test_rn05_data_inexistente_ou_fora_do_formato(texto):
    with pytest.raises(ErroCampo):
        parse_data(texto)


def test_rn05_janela_do_vencimento():
    assert validar_vencimento(date(2026, 11, 16), HOJE)
    assert validar_vencimento(date(2027, 11, 15), HOJE)
    for fora in (date(2026, 11, 15), date(2026, 11, 14), date(2027, 11, 16)):
        with pytest.raises(ErroCampo):
            validar_vencimento(fora, HOJE)


@pytest.mark.parametrize(
    "texto,ok",
    [("2026-11", True), ("2026-13", False), ("2026-00", False), ("202611", False), ("2026-1", False)],
)
def test_rn06_competencia(texto, ok):
    if ok:
        assert validar_competencia(texto) == texto
    else:
        with pytest.raises(ErroCampo):
            validar_competencia(texto)


def test_rn07_email():
    assert validar_email(" financeiro@exemplo.test ") == "financeiro@exemplo.test"
    for ruim in ("a@b", "a b@c.com", "semarroba.com", "a@" + "x" * 250 + ".com", ""):
        with pytest.raises(ErroCampo):
            validar_email(ruim)


@pytest.mark.parametrize("ruim", ["ana,outra@golpe.test", "ana<x>@b.test", "ana;b@golpe.test", '"ana"@b.test'])
def test_rn07_email_que_o_cabecalho_to_leria_como_outro_destinatario_e_recusado(ruim):
    with pytest.raises(ErroCampo):
        validar_email(ruim)


def test_rn07_email_comum_com_ponto_mais_e_hifen_passa():
    assert validar_email("ana.souza+boleto@mail-exemplo.com.br") == "ana.souza+boleto@mail-exemplo.com.br"


def test_rn02_documento_aceita_mascara_e_guarda_so_digitos():
    assert parse_documento("111.444.777-35") == "11144477735"
    assert parse_documento("11.222.333/0001-81") == "11222333000181"
    for ruim in ("111.444.777-36", "abc", "", "123"):
        with pytest.raises(ErroCampo):
            parse_documento(ruim)


def test_rn02_cabecalho_ignora_caixa_acento_e_pontas():
    assert normalizar_cabecalho("  Competência ") == "competencia"
    assert normalizar_cabecalho("NOME") == "nome"


def test_texto_colapsa_espacos_e_quebras_de_linha():
    assert limpar_texto("nome", "Ana\r\n  Souza\t Ltda", obrigatorio=True) == "Ana Souza Ltda"


def test_texto_trunca_em_100_caracteres():
    assert len(limpar_texto("descricao", "x" * 300)) == 100


@pytest.mark.parametrize("sujo", ["veja http://golpe.test", "pague em www.golpe.test", "cobrar R$ 10,00"])
def test_rn33_url_ou_reais_em_texto_livre_e_recusado(sujo):
    with pytest.raises(ErroCampo, match="link nem valor"):
        limpar_texto("descricao", sujo)


def test_texto_aceita_aspas_cifrao_e_angulos_sem_alterar():
    assert limpar_texto("nome", 'Ana "A." <ME> 5$', obrigatorio=True) == 'Ana "A." <ME> 5$'


def _linha_ok(**mudancas):
    base = {
        "nome": "Mariana Souza Ltda",
        "documento": "111.444.777-35",
        "email": "financeiro@exemplo.test",
        "valor": "1.250,00",
        "vencimento": "15/12/2026",
        "competencia": "2026-11",
        "descricao": "Mensalidade de novembro",
    }
    base.update(mudancas)
    return base


def test_validar_linha_ok():
    dados, rejeicoes = validar_linha(2, _linha_ok(), HOJE, MAXIMO)
    assert rejeicoes == []
    assert dados.documento == "11144477735"
    assert dados.valor_cent == 125000
    assert dados.vencimento == date(2026, 12, 15)
    assert dados.linha == 2


def test_rn08_linha_invalida_junta_todos_os_motivos():
    dados, rejeicoes = validar_linha(5, _linha_ok(documento="123", email="x"), HOJE, MAXIMO)
    assert dados is None
    assert {r.coluna for r in rejeicoes} == {"documento", "email"}
    assert all(r.linha == 5 for r in rejeicoes)


def test_descricao_e_opcional():
    bruto = _linha_ok()
    del bruto["descricao"]
    dados, rejeicoes = validar_linha(2, bruto, HOJE, MAXIMO)
    assert rejeicoes == [] and dados.descricao == ""
