"""Command-line run: parse 2GIS URLs into one output file (csv, xlsx, json, html or a leads folder)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .exceptions import ChromeRuntimeException, ChromeUserAbortException
from .logger import logger, setup_cli_logger
from .parser import get_parser
from .writer import get_writer

if TYPE_CHECKING:
    from .config import Configuration


def cli_app(urls: list[str], output_path: str, format: str, config: Configuration) -> None:
    setup_cli_logger(config.log)
    run(urls, output_path, format, config)


def run(urls: list[str], output_path: str, format: str, config: Configuration) -> None:
    """Parse every URL into one writer; errors are logged, never raised."""
    logger.info('Парсинг запущен.')
    try:
        with get_writer(output_path, format, config.writer, config.filters) as writer:
            for url in urls:
                logger.info(f'Парсинг ссылки {url}')
                with get_parser(url,
                                chrome_options=config.chrome,
                                parser_options=config.parser) as parser:
                    try:
                        parser.parse(writer)
                    finally:
                        logger.info('Парсинг ссылки завершён.')
    except (KeyboardInterrupt, ChromeUserAbortException):
        logger.error('Работа парсера прервана пользователем.')
    except Exception as e:
        if isinstance(e, ChromeRuntimeException) and str(e) == 'Tab has been stopped':
            logger.error('Вкладка браузера была закрыта.')
        else:
            logger.error('Ошибка во время работы парсера.', exc_info=True)
    finally:
        logger.info('Парсинг завершён.')
