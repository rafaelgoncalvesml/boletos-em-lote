from __future__ import annotations

import re
from dataclasses import dataclass

_REAIS = re.compile(r"R\$|\d{1,3}(?:\.\d{3})*,\d{2}\b", re.IGNORECASE)
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b")
_URL_COMPLETA = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_VALOR_EM_REAIS = re.compile(r"R\$\s*\d[\d.]*,\d{2}")


@dataclass(frozen=True)
class Veredito:
    ok: bool
    motivo: str = ""


def conferir_partes(saudacao: str, contexto: str) -> Veredito:
    texto = f"{saudacao}\n{contexto}"
    if _REAIS.search(texto):
        return Veredito(False, "o texto do Claude traz valor em reais")
    if _URL.search(texto):
        return Veredito(False, "o texto do Claude traz uma URL")
    if _DATA.search(texto):
        return Veredito(False, "o texto do Claude traz uma data")
    return Veredito(True)


def conferir_final(corpo: str, *, valor: str, vencimento: str, link: str) -> Veredito:
    for nome, trecho in (("valor", valor), ("vencimento", vencimento), ("link", link)):
        if not trecho or trecho not in corpo:
            return Veredito(False, f"o e-mail final não contém o {nome}")
    if any(url.rstrip(".,;)") != link for url in _URL_COMPLETA.findall(corpo)):
        return Veredito(False, "o e-mail final tem uma URL diferente do link do boleto")
    if any(v != valor for v in _VALOR_EM_REAIS.findall(corpo)):
        return Veredito(False, "o e-mail final tem outro valor em reais")
    return Veredito(True)
