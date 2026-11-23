"""SupabaseStore talks to the leadbombing schema (shared Supabase on the server) and lets in only its members."""
import pytest

from leadbombing.web import supabase as sb
from leadbombing.web.supabase import AccessDenied, SupabaseStore

USER_ID = 'a0000000-0000-4000-8000-000000000001'
AUTH_REPLY = {'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600,
              'user': {'id': USER_ID, 'email': 'admin@leadbombing.local', 'user_metadata': {'login': 'admin'}}}


class _Reply:
    def __init__(self, data):
        self.ok, self.status_code = True, 200
        self.content = b'x'
        self.headers = {'Content-Type': 'application/json'}
        self._data = data

    def json(self):
        return self._data


@pytest.fixture()
def calls(monkeypatch):
    seen: list[dict] = []
    members: list[dict] = [{'user_id': USER_ID}]

    def fake_request(method, url, headers=None, **kwargs):
        seen.append({'method': method, 'url': url, 'headers': headers or {}, 'params': kwargs.get('params')})
        if '/auth/v1/token' in url:
            return _Reply(AUTH_REPLY)
        if url.endswith('/rest/v1/members'):
            return _Reply(list(members))
        return _Reply([])

    monkeypatch.setattr(sb.requests, 'request', fake_request)
    return seen, members


def test_rest_reads_and_writes_go_to_the_leadbombing_schema(calls):
    seen, _ = calls
    store = SupabaseStore('http://db', 'key')
    store.list_runs('at', 5)
    store.save_settings('at', {'a': 1})
    read, write = seen
    assert read['headers']['Accept-Profile'] == 'leadbombing' and 'Content-Profile' not in read['headers']
    assert write['headers']['Content-Profile'] == 'leadbombing' and 'Accept-Profile' not in write['headers']


def test_auth_requests_carry_no_schema_profile(calls):
    seen, _ = calls
    SupabaseStore('http://db', 'key').sign_in('admin', 'pw')
    token_call = next(c for c in seen if '/auth/v1/' in c['url'])
    assert 'Accept-Profile' not in token_call['headers'] and 'Content-Profile' not in token_call['headers']


def test_member_signs_in(calls):
    seen, _ = calls
    session = SupabaseStore('http://db', 'key').sign_in('admin', 'pw')
    assert session.user_id == USER_ID
    member_call = next(c for c in seen if c['url'].endswith('/rest/v1/members'))
    assert member_call['params']['user_id'] == f'eq.{USER_ID}'


def test_user_of_another_app_is_not_let_in(calls):
    seen, members = calls
    members.clear()
    with pytest.raises(AccessDenied, match='закрыт доступ'):
        SupabaseStore('http://db', 'key').sign_in('admin', 'pw')
    assert any(c['url'].endswith('/auth/v1/logout') for c in seen)
