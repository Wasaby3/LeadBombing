"""Bathhouse leads output must stay byte-identical to the original template (golden files)."""
import datetime as dt
import json
import pathlib
import shutil

import pytest

import leadbombing.leads.writer as writer_mod
from leadbombing.leads import LeadsWriter

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'
GOLDEN = FIXTURES / 'bani_golden'
HERO = b'\xff\xd8fake-jpeg'


class _FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 16)


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return HERO


def run_bani(base: pathlib.Path, monkeypatch) -> None:
    data = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    with LeadsWriter(str(base)) as w:
        w.fetch_state = lambda path, expr: data['prices'].get(path.split('/')[2])
        for item in data['items']:
            w.write({'result': {'items': [item]}})


def tree(base: pathlib.Path) -> dict[str, bytes]:
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob('*')) if p.is_file()}


def test_bani_output_matches_golden(tmp_path, monkeypatch):
    run_bani(tmp_path, monkeypatch)
    if not GOLDEN.exists():  # first run records the reference output of the original code
        shutil.copytree(tmp_path, GOLDEN)
        pytest.skip('golden recorded')
    assert tree(tmp_path) == tree(GOLDEN)
