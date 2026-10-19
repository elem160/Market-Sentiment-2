import os
import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient, ASGITransport

from app.db.database import Base, get_db
from app.services.finbert_service import FinBERTService
from app.core.models import IngestedArticle
from app.core.enums import ProviderType
from app.main import app

# In-memory SQLite engine for tests
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_database():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def setup_finbert_mock():
    """Ensure FinBERT is in deterministic mock mode for all tests (zero model downloads)."""
    FinBERTService.set_mock_mode()
    yield
    FinBERTService.reset_mock_mode()


@pytest.fixture
def db_session():
    """Provides a fresh isolated database session."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture
async def async_client(db_session):
    """Provides an httpx AsyncClient wired directly to FastAPI with the test DB dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


from datetime import datetime, timezone, timedelta

@pytest.fixture
def sample_aapl_articles() -> list[IngestedArticle]:
    path = os.path.join(os.path.dirname(__file__), "fixtures", "news_aapl_positive.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(timezone.utc)
    return [
        IngestedArticle(
            article_id=d["article_id"],
            provider=ProviderType(d["provider"]),
            source_name=d["source_name"],
            canonical_url=d["canonical_url"],
            title=d["title"],
            summary=d["summary"],
            published_at_utc=now - timedelta(minutes=(30 - idx * 5)),
            retrieved_at_utc=now,
            raw_provider_metadata={},
        )
        for idx, d in enumerate(data)
    ]


@pytest.fixture
def sample_nvda_articles() -> list[IngestedArticle]:
    path = os.path.join(os.path.dirname(__file__), "fixtures", "news_nvda_negative.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(timezone.utc)
    return [
        IngestedArticle(
            article_id=d["article_id"],
            provider=ProviderType(d["provider"]),
            source_name=d["source_name"],
            canonical_url=d["canonical_url"],
            title=d["title"],
            summary=d["summary"],
            published_at_utc=now - timedelta(minutes=(30 - idx * 5)),
            retrieved_at_utc=now,
            raw_provider_metadata={},
        )
        for idx, d in enumerate(data)
    ]

