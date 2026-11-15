from __future__ import annotations


def formatar_reais(cent: int) -> str:
    reais, centavos = divmod(cent, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def formatar_data(iso: str) -> str:
    ano, mes, dia = iso.split("-")
    return f"{dia}/{mes}/{ano}"


def data_curta(iso: str) -> str:
    return formatar_data(iso)[:5]


def competencia_br(competencia: str) -> str:
    ano, mes = competencia.split("-")
    return f"{mes}/{ano}"
