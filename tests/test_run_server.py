"""run_server: in a container the address and the browser come from the environment."""
import pytest

from leadbombing.web import server


@pytest.fixture()
def started(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(server, 'create_app', lambda: type('App', (), {'run': lambda self, **kw: calls.update(kw)})())
    monkeypatch.setattr(server.webbrowser, 'open', lambda url: calls.update(opened=url))
    monkeypatch.delenv('LEADBOMBING_HOST', raising=False)
    monkeypatch.delenv('LEADBOMBING_OPEN_BROWSER', raising=False)
    return calls


def test_defaults_to_localhost_and_opens_the_browser(started):
    server.run_server()
    assert started['host'] == '127.0.0.1' and started['port'] == 8666
    assert started['opened'] == 'http://127.0.0.1:8666/'


def test_container_settings_come_from_the_environment(started, monkeypatch):
    monkeypatch.setenv('LEADBOMBING_HOST', '0.0.0.0')
    monkeypatch.setenv('LEADBOMBING_OPEN_BROWSER', '0')
    server.run_server()
    assert started['host'] == '0.0.0.0' and 'opened' not in started
