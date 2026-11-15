from boletos.lote import analisar
from tests.conftest import CNPJ_1, CPF_1, CPF_2


def _csv(tmp_path, linhas):
    caminho = tmp_path / "a.csv"
    cab = "nome,documento,email,valor,vencimento,competencia,descricao"
    caminho.write_text("\n".join([cab, *linhas]) + "\n", encoding="utf-8")
    return caminho


def _l(doc, valor='"1.250,00"', comp="2026-11", venc="15/12/2026"):
    return f"Ana,{doc},ana@exemplo.test,{valor},{venc},{comp},Mensalidade"


def test_analisa_validas_e_rejeitadas(tmp_path, cfg, hoje):
    arq = _csv(tmp_path, [_l(CPF_1), _l("123"), _l(CNPJ_1, venc="01/01/2020")])
    a = analisar(arq, cfg, hoje)
    assert a.linhas_lidas == 3
    assert len(a.itens) == 1
    assert {(r.linha, r.coluna) for r in a.rejeicoes} == {(3, "documento"), (4, "vencimento")}


def test_rn10_linha_repetida_no_arquivo_vira_aviso_e_e_ignorada(tmp_path, cfg, hoje):
    a = analisar(_csv(tmp_path, [_l(CPF_1), _l(CPF_2), _l(CPF_1)]), cfg, hoje)
    assert len(a.itens) == 2
    aviso = next(x for x in a.avisos if x.tipo == "duplicada_arquivo")
    assert aviso.linha == 4 and "linha 2" in aviso.texto


def test_a2_mesmo_documento_e_competencia_com_valor_diferente_avisa_mas_mantem(tmp_path, cfg, hoje):
    a = analisar(_csv(tmp_path, [_l(CPF_1), _l(CPF_1, valor='"1.300,00"')]), cfg, hoje)
    assert len(a.itens) == 2
    assert [x.tipo for x in a.avisos] == ["competencia_repetida"]


def test_rn09_ordem_das_colunas_nao_muda_a_chave(tmp_path, cfg, hoje):
    a1 = analisar(_csv(tmp_path, [_l(CPF_1)]), cfg, hoje)
    invertido = tmp_path / "b.csv"
    invertido.write_text(
        "competencia,vencimento,valor,email,documento,nome\n"
        f'2026-11,15/12/2026,"1.250,00",ana@exemplo.test,{CPF_1},Ana\n',
        encoding="utf-8",
    )
    a2 = analisar(invertido, cfg, hoje)
    assert a1.itens[0].chave == a2.itens[0].chave
