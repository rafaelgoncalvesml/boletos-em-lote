class ErroBoletos(Exception):
    codigo_saida = 1


class ErroConfig(ErroBoletos):
    codigo_saida = 1


class BancoIndisponivel(ErroBoletos):
    codigo_saida = 1


class CredencialRecusada(ErroBoletos):
    codigo_saida = 1


class EntradaRecusada(ErroBoletos):
    codigo_saida = 2


class LotePausado(ErroBoletos):
    codigo_saida = 3


class TransicaoInvalida(ErroBoletos):
    codigo_saida = 1
