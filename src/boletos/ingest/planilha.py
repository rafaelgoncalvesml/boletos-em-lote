from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from boletos.erros import EntradaRecusada
from boletos.validation.regras import normalizar_cabecalho

COLUNAS_OBRIGATORIAS = ("nome", "documento", "email", "valor", "vencimento", "competencia")


@dataclass(frozen=True)
class Planilha:
    colunas: list[str]
    linhas: list[tuple[int, dict[str, str]]]


def _ler_texto(caminho: Path) -> str:
    bruto = caminho.read_bytes()
    try:
        return bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        return bruto.decode("cp1252")


def _registros_csv(caminho: Path) -> list[list[str]]:
    texto = _ler_texto(caminho)
    if not texto.strip():
        raise EntradaRecusada("A planilha está vazia.")
    primeira = texto.splitlines()[0]
    separador = ";" if primeira.count(";") > primeira.count(",") else ","
    return list(csv.reader(io.StringIO(texto, newline=""), delimiter=separador))


def _celula_xlsx(valor: object, coluna: str) -> str:
    if valor is None:
        return ""
    if isinstance(valor, (datetime, date)):
        dia = valor.date() if isinstance(valor, datetime) else valor
        return dia.strftime("%Y-%m") if coluna == "competencia" else dia.isoformat()
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if coluna == "documento":
            digitos = str(int(valor))
            return digitos.zfill(11 if len(digitos) <= 11 else 14)
        return format(Decimal(str(valor)), "f")
    return str(valor)


def _registros_xlsx(caminho: Path) -> list[list[str]]:
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        linhas = list(wb.worksheets[0].iter_rows(values_only=True))
    finally:
        wb.close()
    if not linhas:
        raise EntradaRecusada("A planilha está vazia.")
    colunas = [normalizar_cabecalho(str(c)) if c is not None else "" for c in linhas[0]]
    registros = [[str(c) if c is not None else "" for c in linhas[0]]]
    for linha in linhas[1:]:
        registros.append([_celula_xlsx(v, colunas[i] if i < len(colunas) else "") for i, v in enumerate(linha)])
    return registros


def ler_planilha(caminho: Path, linhas_por_lote: int) -> Planilha:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise EntradaRecusada(f"Arquivo não encontrado: {caminho}")
    sufixo = caminho.suffix.lower()
    if sufixo == ".csv":
        registros = _registros_csv(caminho)
    elif sufixo == ".xlsx":
        registros = _registros_xlsx(caminho)
    else:
        raise EntradaRecusada("Formato não suportado: use um arquivo CSV ou XLSX.")

    colunas = [normalizar_cabecalho(c) for c in registros[0]]
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if faltando:
        raise EntradaRecusada("Faltam colunas obrigatórias: " + ", ".join(faltando))

    linhas: list[tuple[int, dict[str, str]]] = []
    for numero, registro in enumerate(registros[1:], start=2):
        if not any(c.strip() for c in registro):
            continue
        valores = {col: (registro[i].strip() if i < len(registro) else "") for i, col in enumerate(colunas)}
        linhas.append((numero, valores))

    if not linhas:
        raise EntradaRecusada("A planilha não tem linhas de dados, só o cabeçalho.")
    if len(linhas) > linhas_por_lote:
        raise EntradaRecusada(f"A planilha tem {len(linhas)} linhas e o limite por lote é {linhas_por_lote}.")
    return Planilha(colunas=colunas, linhas=linhas)
