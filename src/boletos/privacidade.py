from __future__ import annotations

import logging
import re

_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def mascarar_documento(doc: str) -> str:
    d = re.sub(r"\D", "", doc)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"**.***.{d[5:8]}/{d[8:12]}-**"
    return "***"


def mascarar_email(email: str) -> str:
    usuario, _, dominio = email.partition("@")
    if not dominio:
        return "***"
    return f"{usuario[:1]}***@{dominio}"


def ocultar(texto: str, segredos: list[str]) -> str:
    for segredo in segredos:
        if segredo:
            texto = texto.replace(segredo, "***")
    texto = _CNPJ.sub(lambda m: mascarar_documento(m.group()), texto)
    texto = _CPF.sub(lambda m: mascarar_documento(m.group()), texto)
    return _EMAIL.sub(lambda m: mascarar_email(m.group()), texto)


class FormatadorSeguro(logging.Formatter):
    def __init__(self, segredos: list[str], fmt: str = "%(asctime)s %(levelname)s %(name)s %(message)s"):
        super().__init__(fmt)
        self._segredos = segredos

    def format(self, record: logging.LogRecord) -> str:
        return ocultar(super().format(record), self._segredos)
