"""Test cases for task processor."""
import pytest
import asyncio
from uuid import uuid4
from unittest.mock import patch, AsyncMock

from app.services.task_processor import process_task, schedule_task
from app.models import Recording, Task


@pytest.mark.asyncio
async def test_process_task_success(test_db):
    """Test successful task processing."""
    # Create test recording and task
    async with test_db() as db:
        recording = Recording(
            filename="test.wav",
            file_path="uploads/test.wav",
            file_size=1024,
            mime_type="audio/wav",
            file_hash="test-hash"
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

    # Mock transcription to return quickly and successfully
    with patch('app.services.task_processor.mock_transcribe', new_callable=AsyncMock) as mock_transcribe:
        mock_transcribe.return_value = "这是测试转写文本"

        # Process task
        await process_task(task_id)

        # Verify task was updated
        async with test_db() as db:
            from sqlalchemy import select
            result = await db.execute(select(Task).where(Task.id == task_id))
            updated_task = result.scalar_one()

            assert updated_task.status == "done"
            assert updated_task.transcript == "这是测试转写文本"
            assert updated_task.error_message is None


@pytest.mark.asyncio
async def test_process_task_failure(test_db):
    """Test task processing failure."""
    # Create test recording and task
    async with test_db() as db:
        recording = Recording(
            filename="test.wav",
            file_path="uploads/test.wav",
            file_size=1024,
            mime_type="audio/wav",
            file_hash="test-hash"
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

    # Mock transcription to fail
    with patch('app.services.task_processor.mock_transcribe', new_callable=AsyncMock) as mock_transcribe:
        mock_transcribe.side_effect = Exception("音频格式解码失败")

        # Process task
        await process_task(task_id)

        # Verify task was marked as failed
        async with test_db() as db:
            from sqlalchemy import select
            result = await db.execute(select(Task).where(Task.id == task_id))
            updated_task = result.scalar_one()

            assert updated_task.status == "failed"
            assert updated_task.transcript is None
            assert "音频格式解码失败" in updated_task.error_message


@pytest.mark.asyncio
async def test_process_task_not_found():
    """Test processing non-existent task."""
    # Should not raise exception, just log error
    fake_id = uuid4()
    await process_task(fake_id)
    # No assertion needed, just verify it doesn't crash


def test_schedule_task():
    """Test task scheduling."""
    # Mock the background task creation
    task_id = uuid4()

    with patch('app.services.task_processor.asyncio.create_task') as mock_create_task:
        mock_task = AsyncMock()
        mock_create_task.return_value = mock_task

        schedule_task(task_id)

        # Verify asyncio.create_task was called
        mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_task_status_transitions(test_db):
    """Test that task status transitions correctly."""
    # Create test data
    async with test_db() as db:
        recording = Recording(
            filename="test.wav",
            file_path="uploads/test.wav",
            file_size=1024,
            mime_type="audio/wav",
            file_hash="test-hash"
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

    # Mock transcription with delay to check intermediate state
    async def slow_transcribe(file_path):
        await asyncio.sleep(0.1)
        return "转写文本"

    with patch('app.services.task_processor.mock_transcribe', side_effect=slow_transcribe):
        # Start processing
        process_coro = process_task(task_id)

        # Give it time to update to transcribing
        await asyncio.sleep(0.05)

        # Check intermediate state
        async with test_db() as db:
            from sqlalchemy import select
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one()
            assert task.status == "transcribing"

        # Wait for completion
        await process_coro

        # Check final state
        async with test_db() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one()
            assert task.status == "done"
