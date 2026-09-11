"""Test cases for automatic retry and concurrency control."""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from app.services.task_processor import (
    process_task_with_retry,
    process_task_with_semaphore,
    _reset_semaphore_for_testing
)


@pytest.fixture(autouse=True)
def reset_semaphore():
    """Reset semaphore before each test."""
    _reset_semaphore_for_testing()
    yield
    _reset_semaphore_for_testing()


@pytest.mark.asyncio
async def test_process_task_with_retry_succeeds_first_attempt():
    """Test that task succeeds on first attempt without retry."""
    task_id = uuid4()

    # Mock successful processing
    with patch('app.services.task_processor.process_task', new_callable=AsyncMock) as mock_process:
        mock_process.return_value = None
        await process_task_with_retry(task_id)

        # Should only be called once (no retries)
        assert mock_process.call_count == 1


@pytest.mark.asyncio
async def test_process_task_with_retry_fails_then_succeeds():
    """Test that task retries after failure and eventually succeeds."""
    task_id = uuid4()

    # Mock AsyncSessionLocal to avoid database calls
    mock_db_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.retry_count = 0

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_db_session.execute.return_value = mock_result

    # Mock: fail twice, then succeed
    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch('app.services.task_processor.process_task', new_callable=AsyncMock) as mock_process:
            mock_process.side_effect = [
                Exception("First failure"),
                Exception("Second failure"),
                None  # Success on third attempt
            ]

            await process_task_with_retry(task_id)

            # Should be called 3 times (initial + 2 retries)
            assert mock_process.call_count == 3


@pytest.mark.asyncio
async def test_process_task_with_retry_exhausts_all_retries():
    """Test that task fails after exhausting all retries."""
    task_id = uuid4()

    # Mock database
    mock_db_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.retry_count = 0
    mock_task.error_message = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_db_session.execute.return_value = mock_result

    # Mock: always fail
    with patch('app.services.task_processor.settings') as mock_settings:
        mock_settings.max_retries = 3

        with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
            mock_session_factory.return_value.__aenter__.return_value = mock_db_session

            with patch('app.services.task_processor.process_task', new_callable=AsyncMock) as mock_process:
                mock_process.side_effect = Exception("Persistent failure")

                await process_task_with_retry(task_id)

                # Should be called 4 times (initial + 3 retries)
                assert mock_process.call_count == 4

                # Verify task was marked as failed
                assert mock_task.status == "failed"
                assert mock_task.retry_count == 3
                assert "Persistent failure" in mock_task.error_message


@pytest.mark.asyncio
async def test_retry_exponential_backoff():
    """Test that retry delays follow exponential backoff (1s, 2s, 4s)."""
    task_id = uuid4()

    # Mock database
    mock_db_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.retry_count = 0
    mock_task.error_message = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_db_session.execute.return_value = mock_result

    delays = []
    original_sleep = asyncio.sleep

    async def mock_sleep(delay):
        delays.append(delay)
        await original_sleep(0)  # Don't actually sleep in tests

    with patch('app.services.task_processor.settings') as mock_settings:
        mock_settings.max_retries = 3

        with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
            mock_session_factory.return_value.__aenter__.return_value = mock_db_session

            with patch('app.services.task_processor.asyncio.sleep', new=mock_sleep):
                with patch('app.services.task_processor.process_task', new_callable=AsyncMock) as mock_process:
                    mock_process.side_effect = [
                        Exception("Fail 1"),
                        Exception("Fail 2"),
                        Exception("Fail 3"),
                        None
                    ]

                    await process_task_with_retry(task_id)

    # Should have delays of 1s, 2s, 4s (2^0, 2^1, 2^2)
    assert len(delays) == 3
    assert delays[0] == 1
    assert delays[1] == 2
    assert delays[2] == 4


@pytest.mark.asyncio
async def test_semaphore_limits_concurrent_tasks():
    """Test that semaphore limits concurrent task processing to 3."""
    # Track concurrent execution
    concurrent_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def mock_task(task_id):
        nonlocal concurrent_count, max_concurrent
        async with lock:
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)

        await asyncio.sleep(0.1)  # Simulate work

        async with lock:
            concurrent_count -= 1

    with patch('app.services.task_processor.settings') as mock_settings:
        mock_settings.max_concurrent_tasks = 3

        with patch('app.services.task_processor.process_task_with_retry', new=mock_task):
            # Schedule 10 tasks
            tasks = [process_task_with_semaphore(uuid4()) for _ in range(10)]
            await asyncio.gather(*tasks)

    # Max concurrent should not exceed 3
    assert max_concurrent <= 3
    assert max_concurrent == 3  # Should actually reach the limit


@pytest.mark.asyncio
async def test_semaphore_queues_excess_tasks():
    """Test that tasks beyond concurrency limit are queued."""
    completed = []

    async def mock_task(task_id):
        await asyncio.sleep(0.05)
        completed.append(task_id)

    with patch('app.services.task_processor.settings') as mock_settings:
        mock_settings.max_concurrent_tasks = 3

        with patch('app.services.task_processor.process_task_with_retry', new=mock_task):
            # Schedule 5 tasks (3 should run, 2 should queue)
            task_ids = [uuid4() for _ in range(5)]
            tasks = [process_task_with_semaphore(tid) for tid in task_ids]

            # Wait a bit, should have ~3 completed
            await asyncio.sleep(0.08)
            first_batch = len(completed)

            # Wait for all to complete
            await asyncio.gather(*tasks)

            assert first_batch <= 3
            assert len(completed) == 5


@pytest.mark.asyncio
async def test_retry_aborts_when_task_deleted():
    """Test that retry loop aborts early when task is deleted from database."""
    task_id = uuid4()

    # Mock database - task exists first time, then deleted
    mock_db_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.retry_count = 0

    mock_result = MagicMock()
    # First call returns task, subsequent calls return None (deleted)
    mock_result.scalar_one_or_none.side_effect = [mock_task, None]
    mock_db_session.execute.return_value = mock_result

    with patch('app.services.task_processor.settings') as mock_settings:
        mock_settings.max_retries = 3

        with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
            mock_session_factory.return_value.__aenter__.return_value = mock_db_session

            with patch('app.services.task_processor.process_task', new_callable=AsyncMock) as mock_process:
                # Always fail
                mock_process.side_effect = Exception("Fail")

                await process_task_with_retry(task_id)

                # Should only be called twice: initial attempt + one retry before discovering deletion
                assert mock_process.call_count == 2
                # Retry count should have been incremented once
                assert mock_task.retry_count == 1
