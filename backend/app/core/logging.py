import logging
import sys

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.handlers = [handler]

    # Quiet noisy third-party loggers unless we're debugging.
    for noisy in ("httpx", "apscheduler"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
