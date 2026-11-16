import os

import pytest

from boletos.config import MODELO_PADRAO
from boletos.mail.composer import RedatorClaude, montar_email

pytestmark = pytest.mark.claude_real


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="defina ANTHROPIC_API_KEY para rodar")
def test_composer_real_escreve_e_passa_no_guard(fazer_cobranca):
    import anthropic

    cliente = anthropic.Anthropic(timeout=20.0, max_retries=1)
    email = montar_email(fazer_cobranca(), RedatorClaude(cliente, MODELO_PADRAO))
    assert email.origem == "claude", email.fallback
