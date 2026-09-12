"""Test cases for task recovery on service startup."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from app.services.task_processor import recover_tasks_on_startup
from app.models import Task, Recording


@pytest.mark.asyncio
async def test_recover_pending_tasks():
    """Test that pending tasks are rescheduled on startup."""
    # Mock database with 2 pending tasks
    task1_id = uuid4()
    task2_id = uuid4()

    # Mock query results - two separate sessions
    interrupted_result = MagicMock()
    interrupted_result.scalars.return_value.all.return_value = []

    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = [task1_id, task2_id]

    # First session for interrupted query, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = interrupted_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # Verify both pending tasks were scheduled
    assert mock_schedule.call_count == 2
    assert result['pending_recovered'] == 2
    assert result['interrupted_reset'] == 0


@pytest.mark.asyncio
async def test_recover_interrupted_tasks():
    """Test that interrupted tasks are reset to pending and rescheduled."""
    # Mock database with 2 interrupted tasks
    interrupted1 = MagicMock(spec=Task)
    interrupted1.id = uuid4()
    interrupted1.status = "transcribing"
    interrupted1.updated_at = datetime.utcnow() - timedelta(minutes=2)  # Recent, but still interrupted
    interrupted1.retry_count = 2
    interrupted1.error_message = "Old error"

    interrupted2 = MagicMock(spec=Task)
    interrupted2.id = uuid4()
    interrupted2.status = "summarizing"
    interrupted2.updated_at = datetime.utcnow() - timedelta(seconds=30)  # Very recent
    interrupted2.retry_count = 1
    interrupted2.error_message = "Another error"

    # Mock query results - two separate sessions
    interrupted_result = MagicMock()
    interrupted_result.scalars.return_value.all.return_value = [interrupted1, interrupted2]

    pending_result = MagicMock()
    # After reset, return task IDs only
    pending_result.scalars.return_value.all.return_value = [interrupted1.id, interrupted2.id]

    # First session for interrupted reset, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = interrupted_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # Verify interrupted tasks were reset
    assert interrupted1.status == "pending"
    assert interrupted2.status == "pending"
    # Verify retry_count and error_message were cleared
    assert interrupted1.retry_count == 0
    assert interrupted2.retry_count == 0
    assert interrupted1.error_message is None
    assert interrupted2.error_message is None

    # Verify interrupted tasks were scheduled
    assert mock_schedule.call_count == 2
    assert result['interrupted_reset'] == 2
    assert result['pending_recovered'] == 2


@pytest.mark.asyncio
async def test_recover_no_tasks():
    """Test recovery when there are no tasks to recover."""
    # Mock empty results - two separate sessions
    interrupted_result = MagicMock()
    interrupted_result.scalars.return_value.all.return_value = []

    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = []

    # First session for interrupted query, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = interrupted_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # No tasks should be scheduled
    assert mock_schedule.call_count == 0
    assert result['pending_recovered'] == 0
    assert result['interrupted_reset'] == 0


@pytest.mark.asyncio
async def test_recover_mixed_tasks():
    """Test recovery with both interrupted and normal pending tasks."""
    # 1 interrupted task
    interrupted = MagicMock(spec=Task)
    interrupted.id = uuid4()
    interrupted.status = "transcribing"
    interrupted.updated_at = datetime.utcnow() - timedelta(minutes=1)
    interrupted.retry_count = 1
    interrupted.error_message = "Error"

    # 2 normal pending task IDs
    pending1_id = uuid4()
    pending2_id = uuid4()

    # Mock query results - two separate sessions
    interrupted_result = MagicMock()
    interrupted_result.scalars.return_value.all.return_value = [interrupted]

    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = [interrupted.id, pending1_id, pending2_id]

    # First session for interrupted reset, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = interrupted_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # Verify interrupted task was reset
    assert interrupted.status == "pending"
    assert interrupted.retry_count == 0
    assert interrupted.error_message is None

    # Verify all tasks were scheduled (1 interrupted + 2 pending)
    assert mock_schedule.call_count == 3
    assert result['interrupted_reset'] == 1
    assert result['pending_recovered'] == 3


@pytest.mark.asyncio
async def test_recover_handles_database_error():
    """Test that recovery handles database errors gracefully."""
    mock_db_session = AsyncMock()
    mock_db_session.execute.side_effect = Exception("Database connection failed")

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            # Should not raise exception
            result = await recover_tasks_on_startup()

    # No tasks should be scheduled due to error
    assert mock_schedule.call_count == 0
    assert result['pending_recovered'] == 0
    assert result['interrupted_reset'] == 0


@pytest.mark.asyncio
async def test_recover_handles_commit_failure():
    """Test that recovery handles commit failures and resets counters."""
    interrupted = MagicMock(spec=Task)
    interrupted.id = uuid4()
    interrupted.status = "transcribing"
    interrupted.updated_at = datetime.utcnow() - timedelta(minutes=1)

    interrupted_result = MagicMock()
    interrupted_result.scalars.return_value.all.return_value = [interrupted]

    mock_db_session = AsyncMock()
    mock_db_session.execute.return_value = interrupted_result
    mock_db_session.commit.side_effect = Exception("Commit failed")

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # Should report 0 interrupted tasks reset due to commit failure
    assert result['interrupted_reset'] == 0
    assert result['pending_recovered'] == 0
    # No tasks should be scheduled
    assert mock_schedule.call_count == 0
