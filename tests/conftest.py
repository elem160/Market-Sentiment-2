"""Shared pytest configuration: throwaway state, no network, frozen clock, fake models.

The environment overrides run before any ``app`` import (environment variables take
precedence over ``.env``), so request handlers, background jobs and tests all share one
temporary SQLite database and the developer's real database and API key are never used.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="sentimentpulse-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db").replace("\\", "/")
os.environ["OPENROUTER_API_KEY"] = ""  # never call OpenRouter from tests
os.environ["ENABLE_LLM"] = "false"  # LLM unit tests enable it explicitly via a fixture
os.environ["APP_ENV"] = "test"
os.environ["HF_HUB_OFFLINE"] = "1"  # slow tests load FinBERT from the local Hugging Face cache only

import asyncio  # noqa: E402
import ipaddress  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import time_machine  # noqa: E402
import yfinance  # noqa: E402
from fakes import KeywordScorer  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.routes import _background_tasks  # noqa: E402
from app.core.enums import ProviderType  # noqa: E402
from app.core.models import IngestedArticle, PipelineDeps  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, run_migrations  # noqa: E402
from app.services.scoring import FinBERTScorer, set_default_scorer  # noqa: E402
from app.services.ticker_service import TickerService  # noqa: E402
from app.utils.rate_limiter import rate_limiter  # noqa: E402

# Wednesday 2026-10-14 11:00 ET: a regular trading session.
FROZEN_NOW = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _is_marked(request: pytest.FixtureRequest, *names: str) -> bool:
    return any(request.node.get_closest_marker(name) for name in names)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Migrate the throwaway database once (exercising the migrations); delete it afterwards."""
    run_migrations()
    yield
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


def _delete_all_rows() -> None:
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):  # child tables first
            conn.execute(table.delete())


@pytest.fixture
def db_session():
    """A session on the app's own ``SessionLocal`` (shared with request handlers and background jobs)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Network guard
# ---------------------------------------------------------------------------

class NetworkBlockedError(OSError):
    """Raised when a test tries to reach a non-loopback host."""


def _is_loopback_host(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    if not isinstance(host, str):
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _network_guard(request, monkeypatch):
    """Reject non-loopback connections and DNS lookups, and stub out yfinance (skipped for ``live``).

    Loopback stays allowed for the Windows asyncio self-pipe. yfinance talks through curl_cffi,
    which bypasses Python sockets, so ``yfinance.Ticker`` is replaced by a stub that raises; tests
    that need Yahoo data patch it explicitly. Any blocked attempt fails the test unless it is
    marked ``allow_blocked_network``, so hidden network calls cannot pass silently.
    """
    if _is_marked(request, "live"):
        yield
        return

    attempts: list[str] = []

    def block(target: str):
        attempts.append(target)
        raise NetworkBlockedError(f"Network access is disabled in tests (attempted {target})")

    def check_address(address) -> None:
        if isinstance(address, tuple) and address and not _is_loopback_host(address[0]):
            block(f"connect {address[0]}:{address[1] if len(address) > 1 else '?'}")

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(sock, address):
        check_address(address)
        return real_connect(sock, address)

    def guarded_connect_ex(sock, address):
        check_address(address)
        return real_connect_ex(sock, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in (None, "") and not _is_loopback_host(host):
            block(f"DNS lookup {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    class OfflineTicker:
        def __init__(self, symbol, *args, **kwargs):
            block(f"yfinance.Ticker({symbol!r})")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(yfinance, "Ticker", OfflineTicker)

    if sys.platform == "win32":
        # The Proactor event loop connects through overlapped I/O, not socket.connect().
        from asyncio import proactor_events

        real_sock_connect = proactor_events.BaseProactorEventLoop.sock_connect

        async def guarded_sock_connect(loop, sock, address):
            check_address(address)
            return await real_sock_connect(loop, sock, address)

        monkeypatch.setattr(proactor_events.BaseProactorEventLoop, "sock_connect", guarded_sock_connect)

    yield

    if attempts and not _is_marked(request, "allow_blocked_network"):
        pytest.fail("Test attempted blocked network access: " + "; ".join(attempts), pytrace=False)


# ---------------------------------------------------------------------------
# Clock and models
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def frozen_now(request) -> Iterator[datetime]:
    """Freeze the clock at ``FROZEN_NOW`` (or ``request.param`` via indirect parametrisation).

    Tests marked ``live`` or ``slow`` keep the real clock.
    """
    if _is_marked(request, "live", "slow"):
        yield datetime.now(timezone.utc)
        return
    target = getattr(request, "param", FROZEN_NOW).astimezone(timezone.utc)
    with time_machine.travel(target, tick=False):
        yield target


@pytest.fixture(autouse=True)
def _finbert_mock(request):
    """Score with the deterministic ``KeywordScorer``; tests marked ``slow`` load the real FinBERT."""
    if _is_marked(request, "slow"):
        real_scorer = FinBERTScorer.get_instance()
        set_default_scorer(real_scorer)
        if hasattr(app, "state"):
            if not hasattr(app.state, "pipeline_deps") or app.state.pipeline_deps is None:
                app.state.pipeline_deps = PipelineDeps(scorer=real_scorer)
            else:
                app.state.pipeline_deps.scorer = real_scorer
        yield
        set_default_scorer(None)
        return

    fake_scorer = KeywordScorer()
    set_default_scorer(fake_scorer)
    if hasattr(app, "state"):
        if not hasattr(app.state, "pipeline_deps") or app.state.pipeline_deps is None:
            app.state.pipeline_deps = PipelineDeps(scorer=fake_scorer)
        else:
            app.state.pipeline_deps.scorer = fake_scorer
    yield
    set_default_scorer(None)


# ---------------------------------------------------------------------------
# Process-wide state and background jobs
# ---------------------------------------------------------------------------

async def drain_background_tasks(timeout: float = 5.0) -> None:
    """Wait for in-app background jobs; cancel whatever is still running after ``timeout``."""
    from app.services.job_manager import get_default_job_manager
    jm = get_default_job_manager()
    await jm.drain(timeout=timeout)

    loop = asyncio.get_running_loop()
    foreign = {t for t in _background_tasks if t.get_loop() is not loop}
    _background_tasks.difference_update(foreign)
    pending = {t for t in _background_tasks if not t.done()}
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout)
    for task in still_running:
        task.cancel()
    if still_running:
        await asyncio.gather(*still_running, return_exceptions=True)


@pytest_asyncio.fixture(autouse=True)
async def _isolated_test(_network_guard, frozen_now, _finbert_mock):
    """Reset process-wide state; drain background jobs (still guarded, frozen and mocked) and wipe rows."""
    rate_limiter.reset()
    TickerService.clear_cache()
    yield
    await drain_background_tasks()
    rate_limiter.reset()
    TickerService.clear_cache()
    _delete_all_rows()


@pytest.fixture
def wait_for_jobs():
    """Await the background jobs started by the test (call it inside the test's patch context)."""
    return drain_background_tasks


@pytest_asyncio.fixture
async def async_client():
    """httpx client wired directly to the FastAPI app (no lifespan; the session fixture migrates)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# Fixture articles
# ---------------------------------------------------------------------------

def _load_fixture_articles(filename: str, now: datetime) -> list[IngestedArticle]:
    """Load fixture headlines published 20, 15, 10… minutes before ``now``."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        data = json.load(f)
    return [
        IngestedArticle(
            article_id=d["article_id"],
            provider=ProviderType(d["provider"]),
            source_name=d["source_name"],
            canonical_url=d["canonical_url"],
            title=d["title"],
            summary=d["summary"],
            published_at_utc=now - timedelta(minutes=20 - idx * 5),
            retrieved_at_utc=now,
            raw_provider_metadata={},
        )
        for idx, d in enumerate(data)
    ]


@pytest.fixture
def sample_aapl_articles(frozen_now) -> list[IngestedArticle]:
    return _load_fixture_articles("news_aapl_positive.json", frozen_now)


@pytest.fixture
def sample_nvda_articles(frozen_now) -> list[IngestedArticle]:
    return _load_fixture_articles("news_nvda_negative.json", frozen_now)
