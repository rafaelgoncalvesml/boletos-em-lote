from email.message import EmailMessage

import pytest

from boletos.mail.sender import SmtpSender
from tests.integration.conftest import porta_livre

pytestmark = pytest.mark.integration


def _eml(tmp_path):
    msg = EmailMessage()
    msg["From"] = "cobranca@exemplo.test"
    msg["To"] = "cliente1@exemplo.test"
    msg["Subject"] = "Boleto de 11/2026, vencimento em 15/12"
    msg.set_content("Olá, Mariana!\nValor: R$ 1.250,00\n", charset="utf-8", cte="quoted-printable")
    caminho = tmp_path / "00001.eml"
    caminho.write_bytes(msg.as_bytes())
    return caminho


def test_envia_para_o_servidor_de_captura(tmp_path, servidor_smtp):
    captura, porta = servidor_smtp
    SmtpSender("127.0.0.1", porta).enviar(_eml(tmp_path))
    assert len(captura.envelopes) == 1
    envelope = captura.envelopes[0]
    assert envelope.rcpt_tos == ["cliente1@exemplo.test"]
    assert b"Subject: Boleto de 11/2026" in envelope.content


def test_servidor_fora_do_ar_levanta_oserror(tmp_path):
    with pytest.raises(OSError):
        SmtpSender("127.0.0.1", porta_livre(), timeout=2.0).enviar(_eml(tmp_path))


def test_nome_local_e_resolvido_uma_vez_por_remetente(tmp_path, servidor_smtp, monkeypatch):
    # getfqdn leva quase 1 s no Windows; resolver a cada e-mail deixava um lote de 500 com minutos a mais
    import socket

    chamadas = []
    original = socket.getfqdn
    monkeypatch.setattr(socket, "getfqdn", lambda *a: chamadas.append(a) or original(*a))
    captura, porta = servidor_smtp
    remetente = SmtpSender("127.0.0.1", porta)
    for _ in range(3):
        remetente.enviar(_eml(tmp_path))
    assert len(captura.envelopes) == 3 and len(chamadas) <= 1
