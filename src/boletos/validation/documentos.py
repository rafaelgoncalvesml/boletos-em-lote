import re

_PESOS_CNPJ = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def _so_ascii_digitos(d: str) -> bool:
    return d.isascii() and d.isdigit()


def digito_cpf(digitos: str) -> int:
    soma = sum(int(d) * p for d, p in zip(digitos, range(len(digitos) + 1, 1, -1), strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def digito_cnpj(digitos: str) -> int:
    pesos = _PESOS_CNPJ[-len(digitos) :]
    soma = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(d: str) -> bool:
    if len(d) != 11 or not _so_ascii_digitos(d) or d == d[0] * 11:
        return False
    return int(d[9]) == digito_cpf(d[:9]) and int(d[10]) == digito_cpf(d[:10])


def cnpj_valido(d: str) -> bool:
    if len(d) != 14 or not _so_ascii_digitos(d) or d == d[0] * 14:
        return False
    return int(d[12]) == digito_cnpj(d[:12]) and int(d[13]) == digito_cnpj(d[:13])


def documento_valido(d: str) -> bool:
    return cpf_valido(d) or cnpj_valido(d)
