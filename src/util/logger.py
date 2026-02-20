import logging
import os
from datetime import datetime

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")
logging.TRACE = TRACE_LEVEL_NUM


def trace(self, message, *args, **kwargs):
    self.log(logging.TRACE, message, *args, **kwargs)


logging.Logger.trace = trace


def setup_logger(
    name: str,
    log_dir: str = "logs",
    level=logging.INFO,
    console_level=logging.INFO,
    log_id: str | None = None,
    log_to_file: bool = True,
):
    # formatter = logging.Formatter(LOG_FORMAT)
    formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")

    logger = logging.getLogger(name)
    logger.setLevel(min(level, console_level))
    # Clear existing handlers so each game gets its own file
    logger.handlers.clear()

    if log_to_file:
        os.makedirs(log_dir, exist_ok=True)
        if log_id is None:
            log_file = os.path.join(
                log_dir, datetime.now().strftime("%Y%m%d-%H%M%S.log")
            )
        else:
            log_file = os.path.join(
                log_dir, datetime.now().strftime("%Y%m%d-%H%M%S-") + log_id + ".log"
            )

        fh = logging.FileHandler(log_file)
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger
