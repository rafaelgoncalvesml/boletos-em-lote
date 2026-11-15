from boletos.formatos import competencia_br, data_curta, formatar_data, formatar_reais


def test_formatos_brasileiros():
    assert formatar_reais(123456) == "R$ 1.234,56"
    assert formatar_reais(5) == "R$ 0,05"
    assert formatar_reais(100000000) == "R$ 1.000.000,00"
    assert formatar_data("2026-12-15") == "15/12/2026"
    assert data_curta("2026-12-15") == "15/12"
    assert competencia_br("2026-11") == "11/2026"
