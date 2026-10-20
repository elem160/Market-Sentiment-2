"""Guards proving the test session never touches real state, OpenRouter or the network (H1, H17).

Assertions compare plain locals only, so a failure can never print the developer's
real API key (pytest would otherwise render the full ``Settings`` repr).
"""
import os
import socket
import tempfile

import pytest
import yfinance
from sqlalchemy.engine import make_url

from app.config import settings
from app.db.database import engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def test_database_is_a_throwaway_temp_file():
    url = make_url(settings.DATABASE_URL)
    backend = url.get_backend_name()
    db_path = _norm(url.database or "")
    temp_root = _norm(tempfile.gettempdir())
    project_db = _norm(os.path.join(PROJECT_ROOT, "data", "sentiment.db"))
    engine_db = _norm(engine.url.database or "")

    assert backend == "sqlite"
    assert os.path.commonpath([db_path, temp_root]) == temp_root
    assert "sentimentpulse-tests-" in db_path
    assert db_path != project_db
    assert engine_db == db_path


def test_llm_is_disabled_and_has_no_api_key():
    api_key_blank = settings.OPENROUTER_API_KEY == ""
    llm_enabled = settings.ENABLE_LLM
    app_env = settings.APP_ENV

    assert api_key_blank, "OPENROUTER_API_KEY must be blank for the whole test session"
    assert llm_enabled is False
    assert app_env == "test"


@pytest.mark.allow_blocked_network
def test_external_hosts_are_blocked():
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 80), timeout=1)
    with pytest.raises(OSError):
        socket.getaddrinfo("news.google.com", 443)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError):
            sock.connect(("93.184.216.34", 80))
    finally:
        sock.close()


@pytest.mark.allow_blocked_network
def test_yfinance_is_stubbed_out():
    with pytest.raises(OSError):
        yfinance.Ticker("AAPL")


def test_loopback_connections_still_work():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=2)
        conn, _ = server.accept()
        conn.close()
        client.close()
    finally:
        server.close()
