"""Test cases for task query endpoints."""
import pytest
import uuid
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Recording, Task


@pytest.fixture
async def test_recording_with_task(test_db: AsyncSession):
    """Create a test recording with a task."""
    async with test_db as db:
        # Create recording
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

        # Create task
        task = Task(
            recording_id=recording.id,
            status="done",
            transcript="Test transcript",
            summary_json={"summary": "Test summary", "key_points": [], "todos": []}
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        return recording, task


@pytest.mark.asyncio
async def test_get_task_status_success(test_recording_with_task):
    """Test getting task status successfully."""
    recording, task = test_recording_with_task

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/tasks/{task.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == str(task.id)
    assert data["recording_id"] == str(recording.id)
    assert data["status"] == "done"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_task_status_not_found():
    """Test getting non-existent task returns 404."""
    non_existent_id = uuid.uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/tasks/{non_existent_id}")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "TASK_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_recording_detail_success(test_recording_with_task):
    """Test getting recording detail successfully."""
    recording, task = test_recording_with_task

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/recordings/{recording.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["recording_id"] == str(recording.id)
    assert data["filename"] == "test.mp3"
    assert data["file_size"] == 1024
    assert "created_at" in data
    assert data["latest_task"] is not None
    assert data["latest_task"]["task_id"] == str(task.id)
    assert data["latest_task"]["status"] == "done"
    assert data["latest_task"]["transcript"] == "Test transcript"
    assert data["latest_task"]["summary"] is not None


@pytest.mark.asyncio
async def test_get_recording_detail_no_task(test_db: AsyncSession):
    """Test getting recording detail when no task exists."""
    async with test_db as db:
        recording = Recording(
            filename="test.mp3",
            file_path="uploads/test.wav",
            file_size=2048,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/mpeg"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/recordings/{recording_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["recording_id"] == str(recording_id)
    assert data["latest_task"] is None


@pytest.mark.asyncio
async def test_get_recording_detail_task_not_done(test_db: AsyncSession):
    """Test that transcript/summary not included when task not done."""
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
            status="transcribing",
            transcript="Partial transcript"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        recording_id = recording.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/recordings/{recording_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["latest_task"]["status"] == "transcribing"
    assert data["latest_task"]["transcript"] is None
    assert data["latest_task"]["summary"] is None


@pytest.mark.asyncio
async def test_get_recording_detail_not_found():
    """Test getting non-existent recording returns 404."""
    non_existent_id = uuid.uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/recordings/{non_existent_id}")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "RECORDING_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_recording_detail_latest_task(test_db: AsyncSession):
    """Test that only the latest task is returned."""
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

        # Create older task
        old_task = Task(
            recording_id=recording.id,
            status="done",
            transcript="Old transcript"
        )
        db.add(old_task)
        await db.commit()

        # Create newer task
        new_task = Task(
            recording_id=recording.id,
            status="pending"
        )
        db.add(new_task)
        await db.commit()
        await db.refresh(new_task)

        recording_id = recording.id
        new_task_id = new_task.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/v1/recordings/{recording_id}")

    assert response.status_code == 200
    data = response.json()
    # Should return the newer task, not the older one
    assert data["latest_task"]["task_id"] == str(new_task_id)
    assert data["latest_task"]["status"] == "pending"
