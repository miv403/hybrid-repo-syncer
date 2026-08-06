"""
Standardized logging configuration for hybrid-syncer.
Provides a central logger writing operational and debug messages to sys.stderr.
"""

import logging
import sys

# Central logger instance for the package
logger = logging.getLogger("hybrid_syncer")


class SyncerFormatter(logging.Formatter):
    """
    Custom formatter that formats messages cleanly.
    In DEBUG mode, adds [DEBUG] prefix to make command tracing explicit.
    """

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno == logging.DEBUG:
            prefix = "[DEBUG] "
            msg = record.getMessage()
            if not msg.startswith("[DEBUG]"):
                return f"{prefix}{msg}"
        return record.getMessage()


def setup_logging(verbose: bool = False, debug: bool = False) -> logging.Logger:
    """
    Configures the global hybrid_syncer logger based on CLI flags.

    - debug=True implies verbose=True and sets level to DEBUG.
    - verbose=True sets level to INFO.
    - default level is WARNING.
    """
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    logger.setLevel(level)

    # Avoid adding duplicate handlers if setup_logging is called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(SyncerFormatter())
        logger.addHandler(handler)
    else:
        logger.handlers[0].setLevel(level)

    return logger
