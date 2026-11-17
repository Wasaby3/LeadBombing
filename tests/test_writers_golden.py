"""CSV / JSON / HTML writers must keep producing byte-identical files (golden files).

`catalog_items.json` is `bani_items.json` with the fields the catalog models require filled in
(locale, type, org.id, rubric ids/kind, contact value) — the leads fixture is too thin for them.
"""
import json
import shutil

import pytest

from leadbombing.writer import WriterOptions, get_writer
from test_leads_golden import FIXTURES

GOLDEN = FIXTURES / 'writers_golden'

CASES = [
    ('result.csv', 'csv', {}),
    ('result_clean.csv', 'csv', {'csv': {'clean': True}}),
    ('result.json', 'json', {}),
    ('result.html', 'html', {}),
]


def write_fixture(path, file_format: str, options: dict) -> None:
    items = json.loads((FIXTURES / 'catalog_items.json').read_text('utf-8'))
    with get_writer(str(path), file_format, WriterOptions(**options)) as writer:
        for item in items:  # wrapped like MainParser._get_state_item
            writer.write({'meta': {'code': 200}, 'result': {'items': [item]}})


@pytest.mark.parametrize('name, file_format, options', CASES)
def test_writer_output_matches_golden(tmp_path, name, file_format, options):
    write_fixture(tmp_path / name, file_format, options)
    golden = GOLDEN / name
    if not golden.exists():  # first run records the reference output of the current code
        GOLDEN.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp_path / name, golden)
        pytest.skip('golden recorded')
    assert (tmp_path / name).read_bytes() == golden.read_bytes()


def test_csv_skips_documents_that_fail_validation(tmp_path, caplog):
    data = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))  # lacks required catalog fields
    with get_writer(str(tmp_path / 'bad.csv'), 'csv', WriterOptions()) as writer:
        writer.write({'meta': {'code': 200}, 'result': {'items': [data['items'][0]]}})
    lines = (tmp_path / 'bad.csv').read_text('utf-8-sig').splitlines()
    assert lines[0] == 'sep=,' and len(lines) == 2  # header only, no row for the invalid document
    assert 'Ошибка парсинга' in caplog.text
