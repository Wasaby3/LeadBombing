"""`leadbombing-cli -i … -o … -f csv` writes the file through the CLI path (parser replaced by fixture items)."""
import json
import sys

import leadbombing.cli as cli_mod
from leadbombing.main import main
from test_leads_golden import FIXTURES


class FakeParser:
    def __init__(self, url, **kw):
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def parse(self, writer):
        for item in json.loads((FIXTURES / 'catalog_items.json').read_text('utf-8')):
            writer.write({'meta': {'code': 200}, 'result': {'items': [item]}})


def test_cli_writes_csv(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(cli_mod, 'get_parser', FakeParser)
    out = tmp_path / 'out.csv'
    monkeypatch.setattr(sys, 'argv', ['leadbombing-cli', '-i', 'https://2gis.ru/moscow/search/Бани',
                                      '-o', str(out), '-f', 'csv', '--writer.csv.clean', 'yes'])
    main()
    lines = out.read_text('utf-8-sig').splitlines()
    assert lines[0] == 'sep=,' and lines[2].startswith('Усадьба Банная,')
    assert len(lines) == 2 + 4  # the duplicate branch is dropped by the default cross-niche dedup
    assert 'Парсинг завершён.' in caplog.text
