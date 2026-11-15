from datetime import date, datetime

import pytest
from openpyxl import Workbook

from boletos.erros import EntradaRecusada
from boletos.ingest.planilha import ler_planilha

CAB = "nome,documento,email,valor,vencimento,competencia,descricao"
LINHA = 'Ana,111.444.777-35,ana@exemplo.test,"1.250,00",15/12/2026,2026-11,Mensalidade'


def _csv(tmp_path, texto, nome="a.csv", codificacao="utf-8"):
    caminho = tmp_path / nome
    caminho.write_bytes(texto.encode(codificacao))
    return caminho


def test_csv_simples_numera_linhas_a_partir_do_cabecalho(tmp_path):
    p = ler_planilha(_csv(tmp_path, f"{CAB}\n{LINHA}\n{LINHA}\n"), 500)
    assert [n for n, _ in p.linhas] == [2, 3]
    assert p.linhas[0][1]["nome"] == "Ana"
    assert p.linhas[0][1]["valor"] == "1.250,00"


def test_csv_do_excel_brasileiro_ponto_e_virgula_cp1252_e_cabecalho_com_acento(tmp_path):
    texto = "Nome;Documento;E-mail;Valor;Vencimento;Competência;Descrição\n"
    texto = texto.replace("E-mail", "email").replace("Descrição", "descricao")
    texto += "José;111.444.777-35;jose@exemplo.test;1250,00;15/12/2026;2026-11;Mensalidade\n"
    p = ler_planilha(_csv(tmp_path, texto, codificacao="cp1252"), 500)
    assert p.linhas[0][1]["nome"] == "José"
    assert p.linhas[0][1]["competencia"] == "2026-11"
    assert p.linhas[0][1]["valor"] == "1250,00"


def test_csv_com_bom_utf8(tmp_path):
    caminho = tmp_path / "bom.csv"
    bom = bytes([0xEF, 0xBB, 0xBF])
    caminho.write_bytes(bom + f"{CAB}\n{LINHA}\n".encode())
    assert ler_planilha(caminho, 500).linhas[0][1]["nome"] == "Ana"


def test_rn02_cabecalho_ignora_caixa_e_espacos(tmp_path):
    texto = " NOME ,Documento,EMAIL,valor,vencimento,competencia\nAna,1,a@b.c,1,2,3\n"
    assert ler_planilha(_csv(tmp_path, texto), 500).linhas[0][1]["nome"] == "Ana"


def test_rn01_coluna_obrigatoria_faltando_lista_as_que_faltam(tmp_path):
    texto = "nome,documento,email\nAna,1,a@b.c\n"
    with pytest.raises(EntradaRecusada) as erro:
        ler_planilha(_csv(tmp_path, texto), 500)
    for faltando in ("valor", "vencimento", "competencia"):
        assert faltando in str(erro.value)


def test_linhas_em_branco_sao_ignoradas(tmp_path):
    p = ler_planilha(_csv(tmp_path, f"{CAB}\n{LINHA}\n,,,,,,\n\n{LINHA}\n"), 500)
    assert len(p.linhas) == 2


def test_rn08_arquivo_acima_do_limite_e_recusado_inteiro(tmp_path):
    texto = CAB + "\n" + "\n".join([LINHA] * 4) + "\n"
    with pytest.raises(EntradaRecusada, match="3"):
        ler_planilha(_csv(tmp_path, texto), 3)


@pytest.mark.parametrize("conteudo", ["", f"{CAB}\n", f"{CAB}\n\n\n"])
def test_planilha_vazia_ou_so_cabecalho_e_recusada(tmp_path, conteudo):
    with pytest.raises(EntradaRecusada, match="linhas de dados|vazia"):
        ler_planilha(_csv(tmp_path, conteudo), 500)


def test_arquivo_inexistente_e_extensao_estranha(tmp_path):
    with pytest.raises(EntradaRecusada, match="não encontrado"):
        ler_planilha(tmp_path / "nao-existe.csv", 500)
    outro = tmp_path / "a.txt"
    outro.write_text("x")
    with pytest.raises(EntradaRecusada, match="CSV ou XLSX"):
        ler_planilha(outro, 500)


def test_xlsx_com_celulas_nativas(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["nome", "documento", "email", "valor", "vencimento", "competencia", "descricao"])
    ws.append(
        ["Ana", 1234567890, "ana@exemplo.test", 1250.5, datetime(2026, 12, 15), datetime(2026, 11, 1), "Mensalidade"]
    )
    ws.append(["Bia", "111.444.777-35", "bia@exemplo.test", "1.250,00", date(2026, 12, 20), "2026-11", None])
    caminho = tmp_path / "a.xlsx"
    wb.save(caminho)
    p = ler_planilha(caminho, 500)
    primeira, segunda = p.linhas[0][1], p.linhas[1][1]
    assert primeira["documento"] == "01234567890"  # CPF numérico perde o zero à esquerda no Excel
    assert primeira["valor"] == "1250.5"
    assert primeira["vencimento"] == "2026-12-15"
    assert primeira["competencia"] == "2026-11"
    assert segunda["descricao"] == ""
