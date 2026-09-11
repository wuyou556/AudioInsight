"""Test fixtures and configuration for pytest."""
import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import Base, get_db
from app.config import settings

# Use test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://audioinsight:password@localhost:5432/audioinsight_test"
)


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio backend for pytest-asyncio."""
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Create test database engine and session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    TestSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    yield TestSessionLocal

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """Create test client with test database."""
    async def override_get_db():
        async with test_db() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_audio_file():
    """Create a sample audio file content."""
    # Return a small WAV file header (valid format)
    return b"RIFF" + b"\x00" * 100  # Minimal WAV file structure


@pytest_asyncio.fixture
async def sample_recording(test_db):
    """Create a sample recording for tests."""
    import uuid
    from app.models import Recording

    async with test_db() as db:
        recording = Recording(
            filename="test.mp3",
            file_path="uploads/test.wav",
            file_size=1024,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    yield recording_id

    # Cleanup handled by test_db fixture dropping all tables


@pytest_asyncio.fixture
async def sample_recording_with_task(test_db):
    """Create a sample recording with a task for tests."""
    import uuid
    from app.models import Recording, Task

    async with test_db() as db:
        recording = Recording(
            filename="test.mp3",
            file_path="uploads/test.wav",
            file_size=1024,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        task = Task(
            recording_id=recording.id,
            status="done",
            transcript="Test transcript",
            summary_json={"summary": "Test summary", "key_points": [], "todos": []}
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        recording_id = recording.id
        task_id = task.id

    yield recording_id, task_id

    # Cleanup handled by test_db fixture dropping all tables


@pytest_asyncio.fixture
async def failed_task(test_db):
    """Create a sample recording with a failed task for retry tests."""
    import uuid
    from app.models import Recording, Task

    async with test_db() as db:
        recording = Recording(
            filename="test.mp3",
            file_path="uploads/test.wav",
            file_size=1024,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        task = Task(
            recording_id=recording.id,
            status="failed",
            error_message="Something went wrong",
            retry_count=0
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id

    yield task_id

    # Cleanup handled by test_db fixture dropping all tables
