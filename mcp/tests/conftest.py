"""Offline guard: a test without the ``network`` marker cannot reach the internet.

Every outbound path used by the server is blocked with a DNS-style error, so
the provider classifies it as an offline failure (no retry, no sleep):

- yfinance (curl_cffi sessions),
- ``urllib.request.urlopen`` (CoinGecko, alternative.me),
- ``requests`` sessions (FMP, Alpha Vantage, REST option backends).

Run ``pytest -m network`` to use the real network.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

_MESSAGE = "Could not resolve host: network disabled for offline tests"


@pytest.fixture(autouse=True)
def _offline_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Block outbound HTTP unless the test is marked ``network``."""
    if request.node.get_closest_marker("network") is not None:
        yield
        return

    try:
        import curl_cffi.requests as curl_requests
        from curl_cffi.requests.exceptions import DNSError

        def _curl_blocked(*_args, **_kwargs):
            raise DNSError(_MESSAGE)

        monkeypatch.setattr(curl_requests.Session, "request", _curl_blocked)
    except ImportError:
        pass

    def _urlopen_blocked(*_args, **_kwargs):
        raise urllib.error.URLError("[Errno -2] Name or service not known (offline test guard)")

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_blocked)

    try:
        import requests

        def _requests_blocked(*_args, **_kwargs):
            raise requests.exceptions.ConnectionError(_MESSAGE)

        monkeypatch.setattr(requests.sessions.Session, "request", _requests_blocked)
    except ImportError:
        pass
    yield
