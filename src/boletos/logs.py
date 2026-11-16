from __future__ import annotations

import logging

from boletos.config import Config
from boletos.privacidade import FormatadorSeguro


def configurar_logs(cfg: Config, nivel: int = logging.INFO) -> logging.Logger:
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("boletos")
    for antigo in [h for h in logger.handlers if getattr(h, "_boletos", False)]:
        logger.removeHandler(antigo)
        antigo.close()
    handler = logging.FileHandler(cfg.logs_dir / "boletos.log", encoding="utf-8")
    handler.setFormatter(FormatadorSeguro(cfg.segredos()))
    handler._boletos = True
    logger.addHandler(handler)
    logger.setLevel(nivel)
    logger.propagate = False
    return logger
