"""Loopback CDP dials must never go through a proxy (#110565).

``websockets>=14`` connects with ``proxy=True`` and resolves the proxy via
``urllib.request.getproxies()``, which on macOS reads the *system* proxy even with no
``*_proxy`` env vars. The browser child env therefore carries loopback ``NO_PROXY`` entries
(both casings, operator entries kept), and the in-process CDP dials pass ``proxy=None``
for loopback URLs only.
"""

import pytest

import tools.browser_session as bs
from agent.proxy_bypass import add_loopback_no_proxy, loopback_connect_kwargs, loopback_request_kwargs


@pytest.fixture
def stub_sanitized_env(monkeypatch):
    """Replace the credential-scrub layer with a fixed dict so the test sees exactly what
    ``build_browser_env`` adds on top."""
    from tools.environments import local
    holder = {}
    monkeypatch.setattr(local, "hermes_subprocess_env", lambda inherit_credentials=False: dict(holder))
    return holder


def test_browser_env_appends_loopback_to_operator_no_proxy(stub_sanitized_env):
    stub_sanitized_env["NO_PROXY"] = "git.internal, 10.0.0.0/8"
    env = bs.build_browser_env()
    assert env["NO_PROXY"] == "git.internal,10.0.0.0/8,127.0.0.1,localhost,::1"
    # urllib/requests read lowercase ``no_proxy`` first, so it must carry the operator entries
    # too; a loopback-only lowercase value would shadow the uppercase NO_PROXY (#156568).
    assert env["no_proxy"] == "git.internal,10.0.0.0/8,127.0.0.1,localhost,::1"


def test_uppercase_only_no_proxy_keeps_operator_entries_in_lowercase():
    # #156568: an operator who sets only NO_PROXY must not lose those hosts from the lowercase
    # no_proxy urllib reads first — a loopback-only lowercase value proxies the CDP dial.
    env = add_loopback_no_proxy({"NO_PROXY": "browser,localhost,127.0.0.1"})
    assert env["no_proxy"] == "browser,localhost,127.0.0.1,::1"
    assert env["NO_PROXY"] == "browser,localhost,127.0.0.1,::1"
    assert "browser" in env["no_proxy"].split(",")


def test_lowercase_only_no_proxy_keeps_operator_entries_in_uppercase():
    env = add_loopback_no_proxy({"no_proxy": "git.internal"})
    assert env["NO_PROXY"] == "git.internal,127.0.0.1,localhost,::1"
    assert env["no_proxy"] == "git.internal,127.0.0.1,localhost,::1"


def test_operator_no_proxy_wildcard_is_left_alone():
    # ``*,127.0.0.1,...`` is no longer the wildcard for urllib/requests: appending would flip a
    # bypass-everything config into proxy-everything-but-loopback.
    assert add_loopback_no_proxy({"NO_PROXY": "*"}) == {"NO_PROXY": "*"}


NO_PROXIES = {"proxies": {"http": None, "https": None}}


@pytest.mark.parametrize("url, expected, http_expected", [
    ("ws://127.0.0.1:9222/devtools/browser/abc", {"proxy": None}, NO_PROXIES),
    ("ws://localhost:9222/devtools/browser/abc", {"proxy": None}, NO_PROXIES),
    ("ws://[::1]:9222/devtools/browser/abc", {"proxy": None}, NO_PROXIES),
    ("http://127.0.0.2:9222", {"proxy": None}, NO_PROXIES),
    ("http://[::ffff:127.0.0.1]:9222", {"proxy": None}, NO_PROXIES),
    ("ws://localhost.evil.com:9222/devtools/browser/abc", {}, {}),
    ("wss://connect.browserbase.com/cdp?apiKey=x", {}, {}),
])
def test_in_process_cdp_dial_disables_proxy_only_for_loopback(url, expected, http_expected):
    assert loopback_connect_kwargs(url) == expected
    assert loopback_request_kwargs(url) == http_expected
