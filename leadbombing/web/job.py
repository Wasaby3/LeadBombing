from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from ..config import Configuration
from ..logger import logger
from ..parser import get_parser
from ..writer import FilterWriter, get_writer
from ..writer.filters import any_filter_enabled
from ..writer.record import extract_record
from ..writer.writers import FileWriter
from .history import History
from .logs import ListLogHandler

# Keep at most this many log lines in memory for the live progress panel.
_MAX_LOG_LINES = 5000


class CollectorWriter(FileWriter):
    """In-memory writer: collects raw catalog documents (no file output).

    Used by the web dashboard so results can be rendered as cards and later
    exported to any format on demand.
    """
    def __init__(self, writer_options) -> None:
        super().__init__('', writer_options)
        self.docs: list[Any] = []
        # District/sheet label for the URL currently being parsed; kept aligned
        # with `docs` so the export can split results onto separate sheets.
        self.labels: list[Optional[str]] = []
        self.current_label: Optional[str] = None

    def __enter__(self) -> 'CollectorWriter':
        return self

    def __exit__(self, *exc_info) -> None:
        pass

    def write(self, catalog_doc: Any) -> None:
        if not self._check_catalog_doc(catalog_doc):
            return
        self.docs.append(catalog_doc)
        self.labels.append(self.current_label)
        if self._options.verbose:
            record = extract_record(catalog_doc)
            logger.info('Парсинг [%d] > %s', len(self.docs),
                        record['name'] if record else '...')


class ParseJob:
    """Background parsing job for the web dashboard (single job at a time)."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._parser = None
        self._cancelled = False
        self.status = 'idle'  # idle | running | done | stopped | error
        self.logs: list[str] = []
        self.error: Optional[str] = None
        self.collector: Optional[CollectorWriter] = None

    @property
    def running(self) -> bool:
        return self.status == 'running'

    @property
    def count(self) -> int:
        return len(self.collector.docs) if self.collector else 0

    def start(self, config: Configuration, urls: list[str],
              labels: Optional[dict[str, str]] = None) -> None:
        with self._lock:
            if self.running:
                raise RuntimeError('Парсинг уже запущен')
            self.status = 'running'
            self.logs = []
            self.error = None
            self._cancelled = False
            self.collector = CollectorWriter(config.writer)

        self._thread = threading.Thread(target=self._run, args=(config, urls, labels or {}),
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._cancelled = True
            if self._parser:
                try:
                    self._parser.close()
                except Exception:
                    pass

    def clear(self) -> bool:
        """Drop the current results/logs (history is untouched). No-op while running."""
        with self._lock:
            if self.running:
                return False
            self.collector = None
            self.logs = []
            self.error = None
            self.status = 'idle'
            return True

    def _run(self, config: Configuration, urls: list[str],
             labels: Optional[dict[str, str]] = None) -> None:
        labels = labels or {}
        handler = ListLogHandler(self.logs, '%(asctime)s | %(message)s', _MAX_LOG_LINES)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)  # ensure INFO progress lines are captured
        try:
            assert self.collector is not None
            writer: FileWriter = self.collector
            if any_filter_enabled(config.filters):
                writer = FilterWriter(self.collector, config.filters)

            logger.info('Парсинг запущен.')
            with writer:
                failed = self._parse_urls(config, urls, labels, writer)

            self.status = 'stopped' if self._cancelled else 'done'
            if self._cancelled:
                logger.info('Парсинг остановлен.')
            elif failed:
                logger.warning('Готово частично: %d из %d ссылок не обработаны.', failed, len(urls))
                logger.info('Парсинг завершён.')
            else:
                logger.info('Парсинг завершён.')
        except Exception as e:
            if self._cancelled:
                # Stopping closes the browser tab mid-request, surfacing as
                # "Tab has been stopped" — a clean stop, not a failure.
                self.status = 'stopped'
                logger.info('Парсинг остановлен.')
            else:
                self.error = str(e)
                self.status = 'error'
                logger.error('Ошибка во время работы парсера.', exc_info=True)
        finally:
            self._parser = None
            self._save_history(urls)
            logger.removeHandler(handler)

    def _parse_urls(self, config: Configuration, urls: list[str], labels: dict[str, str],
                    writer: FileWriter) -> int:
        """Parse each URL into `writer` until cancelled. → number of URLs that failed."""
        assert self.collector is not None
        failed = 0
        for url in urls:
            if self._cancelled:
                break
            # Tag documents from this URL with its district sheet label.
            self.collector.current_label = labels.get(url)
            logger.info('Парсинг ссылки %s', url)
            try:
                self._parser = get_parser(url, chrome_options=config.chrome,
                                          parser_options=config.parser)
                with self._parser:
                    if not self._cancelled:
                        self._parser.parse(writer)
            except Exception as e:
                # A single URL failing (e.g. 2GIS anti-bot timeout) must not
                # abort the whole run — log it, keep what it collected, and
                # continue with the remaining URLs.
                if self._cancelled:
                    break  # clean stop, not a failure
                failed += 1
                logger.error('Ссылка пропущена из-за ошибки: %s', e)
        return failed

    def _save_history(self, urls: list[str]) -> None:
        """Persist whatever was collected — full run, partial stop, or a crash
        mid-run — so records survive reloads and aren't lost on Stop/error."""
        if self.status not in ('done', 'stopped', 'error') or not self.collector or not self.collector.docs:
            return
        try:
            History().save(urls, self.collector.docs,
                           self.collector._options.model_dump(mode='json'),
                           self.collector.labels)
        except Exception as e:
            logger.error('Не удалось сохранить историю: %s', e)

    def results(self) -> list[dict]:
        """Presentation-ready records for the dashboard grid."""
        if not self.collector:
            return []
        out = []
        for doc in self.collector.docs:
            record = extract_record(doc)
            if record:
                out.append(record)
        return out

    def export(self, output_path: str, file_format: str) -> None:
        """Write collected documents to `output_path` in the given format."""
        if not self.collector:
            raise RuntimeError('Нет данных для экспорта')
        # Filters were already applied while collecting; export raw collected docs.
        with get_writer(output_path, file_format, self.collector._options) as writer:
            for doc in self.collector.docs:
                writer.write(doc)
