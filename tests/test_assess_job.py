"""TEMP: one-off assessment of leads saved before the 2GIS booking button was collected (remove with assess_job)."""
import time

import pytest

import leadbombing.leads.writer as writer_mod
import leadbombing.web.assess_job as assess_mod
import leadbombing.web.folders_api as folders_mod
import leadbombing.web.leads_job as job_mod
from fake_store import FakeStore, login
from leadbombing.parser.exceptions import ParserException
from leadbombing.web import create_app
from test_folders_api import PHONE_BUTTON, saved_folder
from test_leads_api import FakeParser
from test_leads_golden import _FixedDate, _Resp


class FakeCards:
    """Stands in for Chrome on 2GIS: firm id → ad actions; records what was asked."""
    def __init__(self, actions: dict, fail: bool = False):
        self.actions, self.fail, self.asked, self.closed = actions, fail, [], False

    def open(self, headless: bool, city: str):
        self.city = city
        return self.fetch, self.close

    def fetch(self, path, expr):
        assert 'searchContext' in expr
        if self.fail:
            raise ParserException('2ГИС не отдал данные (429) — похоже на капчу или блокировку, прогон остановлен.')
        firm_id = path.split('/')[2]
        self.asked.append(firm_id)
        return self.actions.get(firm_id, [])

    def close(self):
        self.closed = True


def assess(client, folder_id):
    assert client.post(f'/api/folders/{folder_id}/assess', json={}).get_json()['ok']
    for _ in range(200):
        s = client.get('/api/folders/assess/status').get_json()
        if s['status'] != 'running':
            return s
        time.sleep(0.02)
    raise AssertionError('оценка не закончилась')


@pytest.fixture()
def client(tmp_path, monkeypatch):
    user_dir = lambda is_config=True: tmp_path / 'user'  # noqa: E731
    monkeypatch.setattr(job_mod, 'get_parser', FakeParser)
    monkeypatch.setattr(job_mod, 'user_path', user_dir)
    monkeypatch.setattr(folders_mod, 'user_path', user_dir)
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    c = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    login(c)
    return c


@pytest.fixture()
def cards(monkeypatch):
    fake = FakeCards({'70000001007499623': PHONE_BUTTON})
    monkeypatch.setattr(assess_mod, 'open_cards', fake.open)
    monkeypatch.setattr(assess_mod, 'PAUSE_S', 0)
    return fake


def test_old_leads_get_priority_comment_and_card_assessment(client, cards):
    folder_id = saved_folder(client)  # saved without button data: priority 0
    s = assess(client, folder_id)
    assert (s['status'], s['done'], s['total'], s['errors']) == ('done', 2, 2, 0) and cards.closed
    assert cards.city == 'moscow'  # Chrome opens the leads' city page, not the bare domain
    leads = {lead['slug']: lead['priority'] for lead in client.get(f'/api/folders/{folder_id}').get_json()['leads']}
    assert leads == {'usadba-bannaya': 5, 'hlebnikovskie-bani': 3}
    card = client.get(f'/api/folders/{folder_id}/item/usadba-bannaya').get_json()
    assert card['crm']['comment'] == 'Сайта нет, кнопка «Забронировать» в 2ГИС — звонок'
    assert card['assessment']['button']['kind'] == 'phone' and card['crm']['status'] == 'not_written'


def test_work_set_by_hand_is_kept_and_assessed_leads_are_not_fetched_again(client, cards):
    folder_id = saved_folder(client)
    item = f'/api/folders/{folder_id}/item/usadba-bannaya'
    client.patch(item, json={'priority': 2, 'comment': 'звонил'})
    assess(client, folder_id)
    crm = client.get(item).get_json()['crm']
    assert (crm['priority'], crm['comment']) == (2, 'звонил')
    assert client.get(item).get_json()['assessment']['priority'] == 5  # the card still shows the assessment

    asked = len(cards.asked)
    s = assess(client, folder_id)
    assert (s['status'], s['total']) == ('done', 0) and len(cards.asked) == asked


def test_captcha_stops_the_assessment_with_a_message(client, monkeypatch):
    fake = FakeCards({}, fail=True)
    monkeypatch.setattr(assess_mod, 'open_cards', fake.open)
    s = assess(client, saved_folder(client))
    assert s['status'] == 'error' and 'капчу' in s['error'] and fake.closed


def test_unknown_folder_is_refused(client, cards):
    r = client.post('/api/folders/999/assess', json={})
    assert r.status_code == 404 and r.get_json()['error'] == 'Папка не найдена'
