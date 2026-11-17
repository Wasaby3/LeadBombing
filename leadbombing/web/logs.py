"""Collect log lines of a background run into a list the UI polls."""
from __future__ import annotations

import logging


class ListLogHandler(logging.Handler):
    """Appends formatted records to `sink`, keeping only the last `max_lines`.

    Never raises: a broken log line must not stop the run it describes.
    """

    def __init__(self, sink: list[str], fmt: str, max_lines: int) -> None:
        super().__init__()
        self._sink = sink
        self._max_lines = max_lines
        self.setFormatter(logging.Formatter(fmt, datefmt='%H:%M:%S'))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._sink.append(self.format(record))
            if len(self._sink) > self._max_lines:
                del self._sink[:len(self._sink) - self._max_lines]
        except Exception:
            pass
