import logging
import os
from datetime import datetime

def setup_logger(
    name: str,
    log_dir: str = "logs",
    level=logging.INFO,
    console_level=logging.ERROR,
):
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, datetime.now().strftime("%Y%m%d-%H%M%S.log"))

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger


    #formatter = logging.Formatter(LOG_FORMAT)
    formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(log_file)
    fh.setLevel(level)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
