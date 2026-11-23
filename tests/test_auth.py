"""Login to the personal account: protected API, admin/admin, logout, token refresh, restore after restart."""
import time

import pytest

from fake_store import FakeStore, login
from leadbombing.web import create_app
from leadbombing.web.account import Accounts
from leadbombing.web.supabase import Session

SECRET = 'test-secret'


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def client(store):
    return create_app(store=store, secret_key=SECRET).test_client()


def test_api_requires_login_but_shell_is_public(client):
    assert client.get('/search').status_code == 200
    assert client.get('/sw.js').status_code == 200
    r = client.get('/api/leads/meta')
    assert r.status_code == 401 and r.get_json() == {'ok': False, 'error': 'Нужно войти'}
    assert client.get('/api/history').status_code == 401
    assert client.post('/api/leads/start', json={}).status_code == 401
    assert client.get('/classic').status_code == 302


def test_login_with_wrong_password_is_rejected(client):
    r = login(client, password='nope')
    assert r.status_code == 401 and r.get_json() == {'ok': False, 'error': 'Неверный логин или пароль'}
    assert client.get('/api/leads/meta').status_code == 401


def test_login_of_non_member_is_forbidden(client, store):
    store.members.clear()
    r = login(client)
    assert r.status_code == 403
    assert r.get_json() == {'ok': False, 'error': 'Этой учётной записи закрыт доступ к LeadBombing'}
    assert client.get('/api/leads/meta').status_code == 401


def test_login_rejects_malformed_body(client):
    assert client.post('/api/auth/login', json={'login': '', 'password': 'x'}).status_code == 400
    assert client.post('/api/auth/login', json={'login': 'admin', 'password': ['admin']}).status_code == 400
    assert client.post('/api/auth/login', data='not json').status_code == 400


def test_login_opens_api_and_me_shows_login(client):
    assert client.get('/api/auth/me').status_code == 401
    r = login(client)
    assert r.status_code == 200 and r.get_json() == {'ok': True, 'login': 'admin'}
    assert client.get('/api/auth/me').get_json() == {'ok': True, 'login': 'admin'}
    assert client.get('/api/leads/meta').status_code == 200
    assert client.get('/classic').status_code == 200


def test_logout_closes_api(client):
    login(client)
    assert client.post('/api/auth/logout').get_json() == {'ok': True}
    assert client.get('/api/leads/meta').status_code == 401
    assert client.get('/api/auth/me').status_code == 401


def test_database_down_gives_readable_error(client, store):
    store.down = True
    r = login(client)
    assert r.status_code == 503 and r.get_json() == {'ok': False, 'error': 'База недоступна'}


def test_session_survives_server_restart(store):
    first = create_app(store=store, secret_key=SECRET).test_client()
    login(first)
    restarted = create_app(store=store, secret_key=SECRET).test_client()
    restarted.set_cookie('session', first.get_cookie('session').value)
    assert restarted.get('/api/auth/me').get_json() == {'ok': True, 'login': 'admin'}
    assert store.refreshed == 1


def test_stale_session_after_restart_asks_to_log_in_again(store):
    first = create_app(store=store, secret_key=SECRET).test_client()
    login(first)
    store._valid_refresh.clear()  # refresh token revoked on the server
    restarted = create_app(store=store, secret_key=SECRET).test_client()
    restarted.set_cookie('session', first.get_cookie('session').value)
    assert restarted.get('/api/leads/meta').status_code == 401


def test_account_refreshes_token_before_it_expires(store):
    accounts = Accounts(store)
    account = accounts.sign_in('admin', 'admin')
    old = account.token()
    account._session = Session(account.user_id, 'admin', old, account.refresh_token, time.time() + 5)
    assert account.token() != old and store.refreshed == 1
    assert account.token() == account.token() and store.refreshed == 1
