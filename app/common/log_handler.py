import logging
import sys


def _build_logger():
    logger = logging.getLogger("fastapi_app")

    # Prevent creation of handlers more than once
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Standard production format
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s "
        "%(message)s  (in %(filename)s:%(lineno)d)"
    )

    # ---- Console (stdout) Handler ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


log = _build_logger()

def handle_global_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        return

    log.critical(
        "UNCAUGHT EXCEPTION",
        exc_info=(exc_type, exc_value, exc_traceback),
    )

sys.excepthook = handle_global_exception