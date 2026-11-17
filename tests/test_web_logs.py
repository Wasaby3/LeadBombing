import logging

from leadbombing.web.logs import ListLogHandler


def test_keeps_last_lines_in_given_format():
    sink: list[str] = []
    log = logging.getLogger('test_web_logs')
    log.propagate = False
    handler = ListLogHandler(sink, '%(levelname)s | %(message)s', max_lines=2)
    log.addHandler(handler)
    try:
        for n in range(3):
            log.warning('line %d', n)
    finally:
        log.removeHandler(handler)
    assert sink == ['WARNING | line 1', 'WARNING | line 2']
