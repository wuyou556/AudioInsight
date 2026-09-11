"""Test cases for task retry endpoint."""
import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Recording, Task


@pytest.mark.asyncio
async def test_retry_task_success(test_db: AsyncSession):
    """Test successfully retrying a failed task."""
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

        # Create failed task
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

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == str(task_id)
    assert data["status"] == "pending"
    assert data["retry_count"] == 1

    # Verify database state
    async with test_db as db:
        from sqlalchemy import select
        result = await db.execute(select(Task).where(Task.id == task_id))
        updated_task = result.scalar_one()
        assert updated_task.status == "pending"
        assert updated_task.retry_count == 1
        assert updated_task.error_message is None


@pytest.mark.asyncio
async def test_retry_task_increments_retry_count(test_db: AsyncSession):
    """Test that retry_count increments on each retry."""
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
            status="failed",
            retry_count=2  # Already retried twice
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 200
    data = response.json()
    assert data["retry_count"] == 3


@pytest.mark.asyncio
async def test_retry_task_not_found():
    """Test retrying non-existent task returns 404."""
    non_existent_id = uuid.uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{non_existent_id}/retry")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "TASK_NOT_FOUND"


@pytest.mark.asyncio
async def test_retry_task_not_failed_pending(test_db: AsyncSession):
    """Test retrying pending task returns 409."""
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
            status="pending"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"]["code"] == "TASK_NOT_FAILED"
    assert data["detail"]["error"]["message"] == "Only failed tasks can be retried"
    assert data["detail"]["error"]["details"]["current_status"] == "pending"


@pytest.mark.asyncio
async def test_retry_task_not_failed_done(test_db: AsyncSession):
    """Test retrying done task returns 409."""
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
            status="done",
            transcript="Success"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"]["code"] == "TASK_NOT_FAILED"


@pytest.mark.asyncio
async def test_retry_task_not_failed_transcribing(test_db: AsyncSession):
    """Test retrying transcribing task returns 409."""
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
            status="transcribing"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_retry_task_clears_error_message(test_db: AsyncSession):
    """Test that retry clears the error message."""
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
            status="failed",
            error_message="Previous error message"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 200

    # Verify error_message cleared
    async with test_db as db:
        from sqlalchemy import select
        result = await db.execute(select(Task).where(Task.id == task_id))
        updated_task = result.scalar_one()
        assert updated_task.error_message is None


@pytest.mark.asyncio
async def test_retry_task_updates_timestamp(test_db: AsyncSession):
    """Test that retry updates the updated_at timestamp."""
    import asyncio
    from datetime import datetime

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
            status="failed"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        task_id = task.id
        original_updated_at = task.updated_at

    # Wait a bit to ensure timestamp difference
    await asyncio.sleep(0.1)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/v1/tasks/{task_id}/retry")

    assert response.status_code == 200
    data = response.json()

    # Parse and compare timestamps
    new_updated_at = datetime.fromisoformat(data["updated_at"].replace('Z', '+00:00'))
    assert new_updated_at > original_updated_at
