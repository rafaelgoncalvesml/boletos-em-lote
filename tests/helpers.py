from types import SimpleNamespace

from boletos.mail.composer import Texto

TEXTO_OK = Texto(saudacao="Olá, Mariana!", contexto="Segue a cobrança da sua mensalidade.")


class RedatorFalso:
    def __init__(self, texto=TEXTO_OK, erro=None):
        self.texto = texto
        self.erro = erro
        self.chamadas = []

    def redigir(self, nome, descricao, competencia):
        self.chamadas.append((nome, descricao, competencia))
        if self.erro:
            raise self.erro
        return self.texto


class ClienteFalso:
    """Imita o cliente do SDK: client.messages.create(...)."""

    def __init__(self, texto, stop_reason="end_turn"):
        self.chamadas = []
        self.messages = self
        self._resposta = SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=texto)])

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        return self._resposta


class SenderFalso:
    def __init__(self, falhas=0):
        self.enviados = []
        self.falhas = falhas

    def enviar(self, caminho):
        if self.falhas > 0:
            self.falhas -= 1
            raise ConnectionRefusedError("servidor SMTP fora do ar")
        self.enviados.append(caminho)
