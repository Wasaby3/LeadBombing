import csv
import json

from leadbombing.leads import LeadsWriter
from leadbombing.leads.generic import COLUMNS
from leadbombing.leads.spheres import get_sphere, sphere_list
from test_leads_golden import FIXTURES, GOLDEN, run_bani, tree, _FixedDate
import leadbombing.leads.writer as writer_mod

SPB = {'code': 'spb', 'name': 'Санкт-Петербург', 'domain': 'ru'}


def _replay(raw, base, sphere=None):
    with LeadsWriter(str(base), sphere=sphere) as w:
        for r in raw:
            w.add(r['item'], r['prices'], r['hero'])
    return w


def test_replay_into_empty_folder_matches_golden(tmp_path, monkeypatch):
    staging = tmp_path / 'staging'
    data = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen',
                        lambda url, timeout=0: __import__('test_leads_golden')._Resp())
    with LeadsWriter(str(staging)) as w:
        w.fetch_state = lambda path, expr: {'prices': data['prices'].get(path.split('/')[2])}
        for item in data['items']:
            w.write({'result': {'items': [item]}})
    _replay(w.raw, tmp_path / 'export')
    assert tree(tmp_path / 'export') == tree(GOLDEN)


def test_replay_keeps_manual_columns_and_slug(tmp_path, monkeypatch):
    target = tmp_path / 'base'
    run_bani(target, monkeypatch)
    rows = list(csv.DictReader((target / 'outreach.csv').open(encoding='utf-8-sig')))
    rows[0]['Статус'], rows[0]['Руководитель'] = 'написал', 'Иван'
    with (target / 'outreach.csv').open('w', encoding='utf-8-sig', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    staging = tmp_path / 'staging'
    data = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))
    with LeadsWriter(str(staging)) as w:
        w.fetch_state = lambda path, expr: {'prices': data['prices'].get(path.split('/')[2])}
        w.write({'result': {'items': [data['items'][0]]}})
    w2 = _replay(w.raw, target)
    rows = list(csv.DictReader((target / 'outreach.csv').open(encoding='utf-8-sig')))
    assert (rows[0]['Статус'], rows[0]['Руководитель']) == ('написал', 'Иван')
    assert len(rows) == 2 and w2.summary['updated'] == 1
    assert sorted(p.name for p in (target / 'tenants').iterdir()) == ['hlebnikovskie-bani', 'usadba-bannaya']


def _firm(**over):
    item = {'id': '70000001000000011', 'name': 'Автосервис Мотор', 'address_name': 'Лиговский, 10',
            'adm_div': [{'type': 'city', 'name': 'Санкт-Петербург'}, {'type': 'district', 'name': 'Центральный'}],
            'rubrics': [{'kind': 'primary', 'name': 'Автосервис'}],
            'contact_groups': [{'contacts': [{'type': 'phone', 'value': '+79110001122'},
                                             {'type': 'whatsapp', 'url': 'https://wa.me/79110001122'}]}],
            'reviews': {'general_rating': 4.9, 'general_review_count': 10}}
    return {**item, **over}


def test_template_sphere_filters_and_layout(tmp_path):
    sphere = get_sphere('auto', [SPB])
    prices = {'updated': None, 'pages': 1, 'items': [
        {'name': 'Замена масла', 'description': '', 'section': 'ТО', 'price': {'fixed': {'value': 1500}}},
        {'name': 'Развал-схождение', 'description': '', 'section': '', 'price': {'from': {'value': 2000}}}]}
    with LeadsWriter(str(tmp_path), sphere=sphere) as w:
        w.fetch_state = lambda path, expr: {'prices': prices}
        w.write({'result': {'items': [_firm()]}})
        w.write({'result': {'items': [_firm(id='2', name='Автомойка Блеск', rubrics=[{'kind': 'primary', 'name': 'Автомойки'}])]}})
        w.write({'result': {'items': [_firm(id='3', name='Мотор Москва', adm_div=[{'type': 'city', 'name': 'Москва'}])]}})
    assert w.summary['added'] == 1 and set(w.summary['skipped']) == {'основная рубрика не «Автосервисы»', 'не Санкт-Петербург'}
    header = (tmp_path / 'outreach.csv').read_text('utf-8-sig').splitlines()[0]
    assert header == ','.join(COLUMNS)
    lead = json.loads((tmp_path / 'leads.json').read_text('utf-8'))[0]
    assert lead['source'] == 'https://2gis.ru/spb/firm/70000001000000011' and lead['sphere'] == 'auto'
    biz = json.loads((tmp_path / 'tenants' / lead['slug'] / 'business.json').read_text('utf-8'))
    assert [s['name'] for s in biz['services']] == ['Замена масла', 'Развал-схождение']
    assert biz['services'][1]['price_from'] is True and biz['contacts']['whatsapp'] == '+79110001122'


def test_lead_gets_priority_from_the_booking_button_read_with_the_prices(tmp_path):
    asked, events = [], []
    actions = [{'caption': 'Записаться', 'type': 'phone', 'value': '+79110001122'}]

    def fetch(path, expr):
        asked.append(path)
        assert 'market' in expr and 'searchContext' in expr  # prices and booking in one request
        return {'prices': None, 'booking': actions}

    with LeadsWriter(str(tmp_path), sphere=get_sphere('auto', [SPB]), on_event=events.append) as w:
        w.fetch_state = fetch
        w.write({'result': {'items': [_firm()]}})
    assert asked == ['/firm/70000001000000011/tab/prices']
    assert events[0]['assessment'] == {'priority': 5, 'note': 'Сайта нет, кнопка «Записаться» в 2ГИС — звонок',
                                       'button': {'kind': 'phone', 'caption': 'Записаться', 'value': '+79110001122'}}
    assert w.raw[0]['booking'] == actions


def test_lead_without_booking_data_has_no_priority(tmp_path):
    events = []
    with LeadsWriter(str(tmp_path), sphere=get_sphere('auto', [SPB]), on_event=events.append) as w:
        w.write({'result': {'items': [_firm()]}})  # no browser: nothing fetched
    assert events[0]['assessment']['priority'] == 0 and w.raw[0]['booking'] is None


def test_sphere_list_has_bani_first():
    ids = [s['id'] for s in sphere_list()]
    assert ids[0] == 'bani' and {'auto', 'beauty', 'dental'} <= set(ids)
