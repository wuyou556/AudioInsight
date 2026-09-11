"""Test cases for recording list pagination endpoint."""
import pytest
import uuid
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Recording, Task


@pytest.mark.asyncio
async def test_list_recordings_empty(test_db: AsyncSession):
    """Test listing recordings when database is empty."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_list_recordings_single(test_db: AsyncSession):
    """Test listing recordings with single item."""
    async with test_db as db:
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

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["recording_id"] == str(recording_id)
    assert data["items"][0]["filename"] == "test.mp3"
    assert data["items"][0]["file_size"] == 1024
    assert data["items"][0]["latest_status"] is None
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_list_recordings_with_task_status(test_db: AsyncSession):
    """Test that latest_status is populated from task."""
    async with test_db as db:
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
            status="done"
        )
        db.add(task)
        await db.commit()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings")

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["latest_status"] == "done"


@pytest.mark.asyncio
async def test_list_recordings_ordered_by_created_at_desc(test_db: AsyncSession):
    """Test recordings are ordered by created_at DESC (newest first)."""
    async with test_db as db:
        # Create recordings with different timestamps
        old_recording = Recording(
            filename="old.mp3",
            file_path="uploads/old.wav",
            file_size=1024,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(old_recording)
        await db.commit()

        new_recording = Recording(
            filename="new.mp3",
            file_path="uploads/new.wav",
            file_size=2048,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(new_recording)
        await db.commit()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    # Newest should be first
    assert data["items"][0]["filename"] == "new.mp3"
    assert data["items"][1]["filename"] == "old.mp3"


@pytest.mark.asyncio
async def test_list_recordings_pagination(test_db: AsyncSession):
    """Test pagination parameters."""
    async with test_db as db:
        # Create 5 recordings
        for i in range(5):
            recording = Recording(
                filename=f"test{i}.mp3",
                file_path=f"uploads/test{i}.wav",
                file_size=1024 * (i + 1),
                file_hash=str(uuid.uuid4()),
                mime_type="audio/mpeg"
            )
            db.add(recording)
        await db.commit()

    # Test page 1 with page_size=2
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page=1&page_size=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2

    # Test page 2
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page=2&page_size=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["page"] == 2

    # Test page 3 (last page with 1 item)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page=3&page_size=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["page"] == 3


@pytest.mark.asyncio
async def test_list_recordings_default_pagination():
    """Test default pagination values."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings")

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_list_recordings_max_page_size(test_db: AsyncSession):
    """Test page_size is capped at 100."""
    async with test_db as db:
        # Create some recordings
        for i in range(10):
            recording = Recording(
                filename=f"test{i}.mp3",
                file_path=f"uploads/test{i}.wav",
                file_size=1024,
                file_hash=str(uuid.uuid4()),
                mime_type="audio/mpeg"
            )
            db.add(recording)
        await db.commit()

    # Try to request 200 items (exceeds max of 100)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page_size=200")

    # FastAPI Query validation should reject this
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recordings_invalid_page():
    """Test invalid page parameter returns 422."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page=0")

    assert response.status_code == 422

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page=-1")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recordings_invalid_page_size():
    """Test invalid page_size parameter returns 422."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page_size=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_recordings_latest_task_only(test_db: AsyncSession):
    """Test that only the latest task status is shown."""
    async with test_db as db:
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

        # Create old task
        old_task = Task(
            recording_id=recording.id,
            status="done"
        )
        db.add(old_task)
        await db.commit()

        # Create new task
        new_task = Task(
            recording_id=recording.id,
            status="pending"
        )
        db.add(new_task)
        await db.commit()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings")

    assert response.status_code == 200
    data = response.json()
    # Should show latest task status
    assert data["items"][0]["latest_status"] == "pending"


@pytest.mark.asyncio
async def test_list_recordings_empty_page(test_db: AsyncSession):
    """Test requesting a page beyond available data returns empty items."""
    async with test_db as db:
        recording = Recording(
            filename="test.mp3",
            file_path="uploads/test.wav",
            file_size=1024,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(recording)
        await db.commit()

    # Request page 10 when only 1 item exists
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/recordings?page=10&page_size=20")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 1
    assert data["page"] == 10
