"""Test cases for recording deletion endpoint."""
import pytest
import uuid
import os
from pathlib import Path
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.models import Recording, Task
from app.config import settings


@pytest.mark.asyncio
async def test_delete_recording_success(test_db: AsyncSession, tmp_path):
    """Test successfully deleting a recording with its file."""
    # Create a temporary file
    test_file = tmp_path / "test_audio.wav"
    test_file.write_bytes(b"test audio content")

    async with test_db as db:
        recording = Recording(
            filename="test_audio.wav",
            file_path=str(test_file),
            file_size=len(b"test audio content"),
            file_hash=str(uuid.uuid4()),
            mime_type="audio/wav"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    # Verify file exists
    assert test_file.exists()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(f"/v1/recordings/{recording_id}")

    assert response.status_code == 204
    assert response.content == b""

    # Verify file deleted
    assert not test_file.exists()

    # Verify database record deleted
    async with test_db as db:
        result = await db.execute(
            select(Recording).where(Recording.id == recording_id)
        )
        deleted_recording = result.scalar_one_or_none()
        assert deleted_recording is None


@pytest.mark.asyncio
async def test_delete_recording_not_found():
    """Test deleting non-existent recording returns 404."""
    non_existent_id = uuid.uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(f"/v1/recordings/{non_existent_id}")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "RECORDING_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_recording_cascades_tasks(test_db: AsyncSession, tmp_path):
    """Test that deleting recording also deletes associated tasks (CASCADE)."""
    test_file = tmp_path / "test.wav"
    test_file.write_bytes(b"test")

    async with test_db as db:
        recording = Recording(
            filename="test.wav",
            file_path=str(test_file),
            file_size=4,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/wav"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        # Create multiple tasks
        task1 = Task(recording_id=recording.id, status="done")
        task2 = Task(recording_id=recording.id, status="failed")
        db.add(task1)
        db.add(task2)
        await db.commit()
        await db.refresh(task1)
        await db.refresh(task2)

        recording_id = recording.id
        task1_id = task1.id
        task2_id = task2.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(f"/v1/recordings/{recording_id}")

    assert response.status_code == 204

    # Verify tasks deleted (CASCADE)
    async with test_db as db:
        result = await db.execute(select(Task).where(Task.id == task1_id))
        assert result.scalar_one_or_none() is None

        result = await db.execute(select(Task).where(Task.id == task2_id))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_recording_file_not_exist(test_db: AsyncSession):
    """Test deleting recording when physical file doesn't exist."""
    async with test_db as db:
        recording = Recording(
            filename="missing.wav",
            file_path="/nonexistent/path/missing.wav",
            file_size=1024,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/wav"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(f"/v1/recordings/{recording_id}")

    # Should succeed even if file doesn't exist
    assert response.status_code == 204

    # Verify database record deleted
    async with test_db as db:
        result = await db.execute(
            select(Recording).where(Recording.id == recording_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_recording_file_deletion_fails(test_db: AsyncSession, tmp_path, monkeypatch):
    """Test that database deletion proceeds even if file deletion fails."""
    test_file = tmp_path / "test.wav"
    test_file.write_bytes(b"test")

    async with test_db as db:
        recording = Recording(
            filename="test.wav",
            file_path=str(test_file),
            file_size=4,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/wav"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    # Mock os.remove to raise an exception
    def mock_remove(path):
        raise PermissionError("Simulated permission error")

    monkeypatch.setattr(os, "remove", mock_remove)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(f"/v1/recordings/{recording_id}")

    # Should still succeed (204) even though file deletion failed
    assert response.status_code == 204

    # Verify database record deleted
    async with test_db as db:
        result = await db.execute(
            select(Recording).where(Recording.id == recording_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_recording_multiple_times(test_db: AsyncSession, tmp_path):
    """Test that deleting same recording twice returns 404 on second attempt."""
    test_file = tmp_path / "test.wav"
    test_file.write_bytes(b"test")

    async with test_db as db:
        recording = Recording(
            filename="test.wav",
            file_path=str(test_file),
            file_size=4,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/wav"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    async with AsyncClient(app=app, base_url="http://test") as client:
        # First deletion
        response1 = await client.delete(f"/v1/recordings/{recording_id}")
        assert response1.status_code == 204

        # Second deletion (should fail)
        response2 = await client.delete(f"/v1/recordings/{recording_id}")
        assert response2.status_code == 404


@pytest.mark.asyncio
async def test_delete_recording_relative_path(test_db: AsyncSession):
    """Test deleting recording with relative file path."""
    # Create uploads directory if it doesn't exist
    uploads_dir = Path(settings.upload_dir)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Create test file
    test_file = uploads_dir / f"test_{uuid.uuid4()}.wav"
    test_file.write_bytes(b"test content")

    relative_path = f"uploads/{test_file.name}"

    async with test_db as db:
        recording = Recording(
            filename=test_file.name,
            file_path=relative_path,
            file_size=12,
            file_hash=str(uuid.uuid4()),
            mime_type="audio/wav"
        )
        db.add(recording)
        await db.commit()
        await db.refresh(recording)

        recording_id = recording.id

    assert test_file.exists()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(f"/v1/recordings/{recording_id}")

    assert response.status_code == 204

    # Verify file deleted
    assert not test_file.exists()

    # Verify database record deleted
    async with test_db as db:
        result = await db.execute(
            select(Recording).where(Recording.id == recording_id)
        )
        assert result.scalar_one_or_none() is None
