"""Logging helpers for PASM CLI/tools."""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    from loguru import logger as _loguru_logger

    _HAS_LOGURU = True
except Exception:  # pragma: no cover - fallback path
    _loguru_logger = None
    _HAS_LOGURU = False


class _StdLoggerAdapter:
    """Small adapter exposing loguru-like methods."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("pasm")
        self._configured = False

    def configure(self, verbose: bool = False) -> None:
        if self._configured:
            return
        level = logging.DEBUG if verbose else logging.INFO
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.handlers.clear()
        self._logger.setLevel(level)
        self._logger.addHandler(handler)
        self._configured = True

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(message, *args, **kwargs)


_std_logger = _StdLoggerAdapter()


def configure_logging(verbose: bool = False) -> None:
    """Configure logging sinks/level for CLI execution."""
    if _HAS_LOGURU:
        level = "DEBUG" if verbose else "INFO"
        _loguru_logger.remove()
        _loguru_logger.add(
            sys.stderr,
            level=level,
            format="{message}",
            colorize=sys.stderr.isatty(),
        )
    else:  # pragma: no cover - fallback path
        _std_logger.configure(verbose=verbose)


logger = _loguru_logger if _HAS_LOGURU else _std_logger

