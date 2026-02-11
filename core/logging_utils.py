from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple


def create_session_logger(*, log_dir: str, debug: bool) -> Tuple[logging.Logger, str]:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = directory / f"session_{timestamp}.log"

    logger_name = f"agent_suite_{timestamp}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

    return logger, str(log_path)
