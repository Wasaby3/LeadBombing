"""Leads run: instant stop, resume from the same city and page, clearing the found leads."""
import json
import re
import threading
import time

import pytest

import leadbombing.leads.writer as writer_mod
import leadbombing.web.leads_job as job_mod
from fake_store import FakeStore, login
from leadbombing.leads import LeadsWriter
from leadbombing.leads.spheres import get_sphere
from leadbombing.leads.writer import RunCancelled
from leadbombing.web import create_app
from test_leads_golden import FIXTURES, _FixedDate, _Resp

PAGE_SIZE = 2
CLOSE_DELAY_S = 1.0  # a real Chrome takes a while to quit; stop must not wait for it
DATA = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))


class PagedParser:
    """Two firms per page; `/page/N` in the URL starts there. Blocks before `block_firm` until closed."""
    instances: list['PagedParser'] = []
    block_firm: str | None = None

    def __init__(self, url, chrome_options=None, parser_options=None):
        self.url = url
        self.max = parser_options.max_records
        self.page = 1
        self.skipped: list[str] = []
        self.closed = threading.Event()
        PagedParser.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def close(self):
        if not self.closed.is_set():
            self.closed.set()
            time.sleep(CLOSE_DELAY_S)

    def parse(self, writer):
        writer.fetch_state = lambda path, expr: {'prices': DATA['prices'].get(path.split('/')[2])}
        m = re.search(r'/page/(\d+)', self.url)
        written = 0
        pages = range(int(m.group(1)) if m else 1, len(DATA['items']) // PAGE_SIZE + 2)
        for self.page in pages:
            for item in DATA['items'][(self.page - 1) * PAGE_SIZE:self.page * PAGE_SIZE]:
                firm_id = item['id'].split('_')[0]
                skip = getattr(writer, 'skip_firm', None)
                if skip and skip(firm_id):
                    self.skipped.append(firm_id)
                    continue
                if item['id'] == PagedParser.block_firm:
                    PagedParser.block_firm = None
                    self.closed.wait(5)
                if self.closed.is_set():
                    raise RuntimeError('Tab has been stopped')
                writer.write({'result': {'items': [item]}})
                written += 1
                if written >= self.max:
                    return


@pytest.fixture()
def client(tmp_path, monkeypatch):
    PagedParser.instances = []
    PagedParser.block_firm = None
    monkeypatch.setattr(job_mod, 'get_parser', PagedParser)
    monkeypatch.setattr(job_mod, 'user_path', lambda is_config=True: tmp_path / 'user')
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    c = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    login(c)
    return c


def status(client):
    return client.get('/api/leads/status?cursor=0').get_json()


def wait_idle(client):
    for _ in range(400):
        s = status(client)
        if s['status'] != 'running' and not s['busy']:
            return s
        time.sleep(0.02)
    raise AssertionError('run did not finish')


def wait_events(client, n):
    for _ in range(400):
        s = status(client)
        if len(s['events']) >= n:
            return s
        time.sleep(0.02)
    raise AssertionError(f'fewer than {n} events')


def lead_slugs(s):
    return [e['slug'] for e in s['events'] if e['type'] == 'lead']


def start_free_search(client, limit=10):
    PagedParser.block_firm = '70000001000000004'  # second firm of page 2
    body = {'sphere': 'custom', 'query': 'бани', 'cities': ['moscow', 'spb'], 'limit': limit}
    assert client.post('/api/leads/start', json=body).get_json()['ok']
    return wait_events(client, 3)


def test_stop_is_instant_and_keeps_no_firm_error(client):
    start_free_search(client)

    began = time.monotonic()
    assert client.post('/api/leads/stop').get_json()['ok']
    assert time.monotonic() - began < CLOSE_DELAY_S / 2
    assert status(client)['status'] == 'stopped'

    s = wait_idle(client)
    assert s['status'] == 'stopped' and s['resumable']
    assert lead_slugs(s) == ['usadba-bannaya', 'hlebnikovskie-bani', 'fitnes-klub-sila']
    assert not [e for e in s['events'] if e['type'] == 'skip']
    assert s['params'] == {'sphere': 'custom', 'query': 'бани', 'cities': ['moscow', 'spb'], 'limit': 10}


def test_resume_continues_from_the_same_city_and_page(client):
    start_free_search(client)
    client.post('/api/leads/stop')
    wait_idle(client)

    assert client.post('/api/leads/resume', json={'limit': 10}).get_json()['ok']
    s = wait_idle(client)

    assert s['status'] == 'done' and not s['resumable']
    assert lead_slugs(s) == ['usadba-bannaya', 'hlebnikovskie-bani', 'fitnes-klub-sila']
    resumed = PagedParser.instances[1]
    assert resumed.url.endswith('/page/2') and resumed.max == 10 - 3
    # done before the stop (and its branch on page 3), not fetched again
    assert resumed.skipped == ['70000001000000003', '70000001007499623']
    assert [p.url.split('/')[3] for p in PagedParser.instances[1:]] == ['moscow', 'spb']
    reasons = [e['reason'] for e in s['events'] if e['type'] == 'skip']
    assert reasons.count('не из выбранных городов') == 1 and 'ошибка обработки' not in reasons
    assert client.get('/api/leads/item/fitnes-klub-sila').status_code == 200


def test_resume_is_refused_after_a_finished_run(client):
    assert client.post('/api/leads/resume', json={}).status_code == 409
    client.post('/api/leads/start', json={'sphere': 'custom', 'query': 'бани', 'cities': ['moscow'], 'limit': 10})
    s = wait_idle(client)
    assert s['status'] == 'done' and not s['resumable']
    assert client.post('/api/leads/resume', json={}).status_code == 409


def test_clear_empties_the_run(client):
    start_free_search(client)
    assert client.post('/api/leads/clear').status_code == 409  # still running
    client.post('/api/leads/stop')
    wait_idle(client)

    assert client.post('/api/leads/clear').get_json()['ok']
    s = status(client)
    assert s['status'] == 'idle' and s['events'] == [] and not s['resumable'] and s['params'] is None
    assert client.get('/api/leads/item/usadba-bannaya/hero').status_code == 404  # staging folder is gone
    assert client.post('/api/leads/export', json={'path': '/tmp/x'}).status_code == 409


def test_writer_stops_instead_of_skipping_a_firm_when_cancelled(tmp_path):
    events = []
    cancelled = threading.Event()

    def broken_fetch(path, expr):
        cancelled.set()
        raise RuntimeError('Tab has been stopped')

    sphere = get_sphere('custom', [{'code': 'moscow', 'name': 'Москва', 'domain': 'ru'}], 'бани')
    with LeadsWriter(str(tmp_path), sphere=sphere, on_event=events.append) as w:
        w.cancelled = cancelled.is_set
        w.fetch_state = broken_fetch
        with pytest.raises(RunCancelled):
            w.write({'result': {'items': [DATA['items'][1]]}})
        assert events == [] and w.summary['errors'] == []

        w.mark_resume()
        assert not w.skip_firm('70000001000000002')  # interrupted firm is fetched again
        cancelled.clear()
        w.fetch_state = lambda path, expr: None
        w.write({'result': {'items': [DATA['items'][1]]}})
        assert [e['type'] for e in events] == ['lead']
        w.mark_resume()
        assert w.skip_firm('70000001000000002')
