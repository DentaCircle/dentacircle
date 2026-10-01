"""Logger levels for the API. Uvicorn supplies the handlers when the server runs."""

import logging


def configure_logging(level: str) -> None:
    numeric = logging.getLevelNamesMapping()[level]
    logger = logging.getLogger("dentacircle")
    logger.setLevel(numeric)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > numeric:
        root.setLevel(numeric)
