import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from secfsn.config.core import LOG_DIR


_LOGGER_CACHE = {}


def get_logger(name: str) -> logging.Logger:
    """Create/get a module-level logger with file + console handlers."""
    if name in _LOGGER_CACHE:
        return _LOGGER_CACHE[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    log_path = Path(LOG_DIR) / f"{name}.log"
    fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3)
    fh.setFormatter(formatter)
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(ch)

    _LOGGER_CACHE[name] = logger
    return logger
