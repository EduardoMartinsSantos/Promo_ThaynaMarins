import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console — substitui caracteres não suportados pelo codec do terminal
    # (evita crash com emojis/acentos em nomes de produtos no Windows)
    stream = open(
        sys.stdout.fileno(), mode="w", encoding=sys.stdout.encoding,
        errors="replace", buffering=1, closefd=False,
    )
    sh = logging.StreamHandler(stream)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    # Arquivo rotativo (10 MB × 5 backups)
    fh = RotatingFileHandler(
        LOG_DIR / f"{name}.log", maxBytes=10 * 1024 * 1024, backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger
