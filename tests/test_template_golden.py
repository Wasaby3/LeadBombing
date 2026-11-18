"""Template-sphere leads output (free search, Moscow) must stay byte-identical (golden files)."""
import json
import pathlib
import shutil

import pytest

import leadbombing.leads.writer as writer_mod
from leadbombing.leads import LeadsWriter
from leadbombing.leads.spheres import MOSCOW, get_sphere
from test_leads_golden import FIXTURES, _FixedDate, _Resp, tree

GOLDEN = FIXTURES / 'custom_golden'


def run_custom(base: pathlib.Path, monkeypatch) -> None:
    data = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    with LeadsWriter(str(base), sphere=get_sphere('custom', [MOSCOW], 'Баня')) as w:
        w.fetch_state = lambda path, expr: {'prices': data['prices'].get(path.split('/')[2])}
        for item in data['items']:
            w.write({'result': {'items': [item]}})


def test_custom_sphere_output_matches_golden(tmp_path, monkeypatch):
    run_custom(tmp_path, monkeypatch)
    if not GOLDEN.exists():  # first run records the reference output of the current code
        shutil.copytree(tmp_path, GOLDEN)
        pytest.skip('golden recorded')
    assert tree(tmp_path) == tree(GOLDEN)
