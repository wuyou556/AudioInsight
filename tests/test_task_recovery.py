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
    zombie_result = MagicMock()
    zombie_result.scalars.return_value.all.return_value = []

    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = [task1_id, task2_id]

    # First session for zombie query, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = zombie_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # Verify both pending tasks were scheduled
    assert mock_schedule.call_count == 2
    assert result['pending_recovered'] == 2
    assert result['zombie_reset'] == 0


@pytest.mark.asyncio
async def test_recover_zombie_tasks():
    """Test that zombie tasks are reset to pending and rescheduled."""
    # Mock database with 2 zombie tasks
    mock_db_session = AsyncMock()

    now = datetime.utcnow()
    old_time = now - timedelta(minutes=10)

    zombie1 = MagicMock(spec=Task)
    zombie1.id = uuid4()
    zombie1.status = "transcribing"
    zombie1.updated_at = old_time
    zombie1.retry_count = 2
    zombie1.error_message = "Old error"

    zombie2 = MagicMock(spec=Task)
    zombie2.id = uuid4()
    zombie2.status = "summarizing"
    zombie2.updated_at = old_time
    zombie2.retry_count = 1
    zombie2.error_message = "Another error"

    # Mock query results - two separate sessions
    zombie_result = MagicMock()
    zombie_result.scalars.return_value.all.return_value = [zombie1, zombie2]

    pending_result = MagicMock()
    # After reset, return task IDs only
    pending_result.scalars.return_value.all.return_value = [zombie1.id, zombie2.id]

    # First session for zombie reset, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = zombie_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            with patch('app.services.task_processor.settings') as mock_settings:
                mock_settings.zombie_task_timeout = 300

                result = await recover_tasks_on_startup()

    # Verify zombies were reset
    assert zombie1.status == "pending"
    assert zombie2.status == "pending"
    # Verify retry_count and error_message were cleared
    assert zombie1.retry_count == 0
    assert zombie2.retry_count == 0
    assert zombie1.error_message is None
    assert zombie2.error_message is None

    # Verify zombies were scheduled
    assert mock_schedule.call_count == 2
    assert result['zombie_reset'] == 2
    assert result['pending_recovered'] == 2


@pytest.mark.asyncio
async def test_recover_no_tasks():
    """Test recovery when there are no tasks to recover."""
    # Mock empty results - two separate sessions
    zombie_result = MagicMock()
    zombie_result.scalars.return_value.all.return_value = []

    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = []

    # First session for zombie query, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = zombie_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            result = await recover_tasks_on_startup()

    # No tasks should be scheduled
    assert mock_schedule.call_count == 0
    assert result['pending_recovered'] == 0
    assert result['zombie_reset'] == 0


@pytest.mark.asyncio
async def test_recover_mixed_tasks():
    """Test recovery with both zombie and normal pending tasks."""
    now = datetime.utcnow()
    old_time = now - timedelta(minutes=10)

    # 1 zombie task
    zombie = MagicMock(spec=Task)
    zombie.id = uuid4()
    zombie.status = "transcribing"
    zombie.updated_at = old_time
    zombie.retry_count = 1
    zombie.error_message = "Error"

    # 2 normal pending task IDs
    pending1_id = uuid4()
    pending2_id = uuid4()

    # Mock query results - two separate sessions
    zombie_result = MagicMock()
    zombie_result.scalars.return_value.all.return_value = [zombie]

    pending_result = MagicMock()
    pending_result.scalars.return_value.all.return_value = [zombie.id, pending1_id, pending2_id]

    # First session for zombie reset, second for pending query
    mock_db_sessions = [AsyncMock(), AsyncMock()]
    mock_db_sessions[0].execute.return_value = zombie_result
    mock_db_sessions[1].execute.return_value = pending_result

    session_iter = iter(mock_db_sessions)

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = lambda: next(session_iter)

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            with patch('app.services.task_processor.settings') as mock_settings:
                mock_settings.zombie_task_timeout = 300

                result = await recover_tasks_on_startup()

    # Verify zombie was reset
    assert zombie.status == "pending"
    assert zombie.retry_count == 0
    assert zombie.error_message is None

    # Verify all tasks were scheduled (1 zombie + 2 pending)
    assert mock_schedule.call_count == 3
    assert result['zombie_reset'] == 1
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
    assert result['zombie_reset'] == 0


@pytest.mark.asyncio
async def test_recover_handles_commit_failure():
    """Test that recovery handles commit failures and resets counters."""
    zombie = MagicMock(spec=Task)
    zombie.id = uuid4()
    zombie.status = "transcribing"
    zombie.updated_at = datetime.utcnow() - timedelta(minutes=10)

    zombie_result = MagicMock()
    zombie_result.scalars.return_value.all.return_value = [zombie]

    mock_db_session = AsyncMock()
    mock_db_session.execute.return_value = zombie_result
    mock_db_session.commit.side_effect = Exception("Commit failed")

    with patch('app.services.task_processor.AsyncSessionLocal') as mock_session_factory:
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch('app.services.task_processor.schedule_task') as mock_schedule:
            with patch('app.services.task_processor.settings') as mock_settings:
                mock_settings.zombie_task_timeout = 300

                result = await recover_tasks_on_startup()

    # Should report 0 zombies reset due to commit failure
    assert result['zombie_reset'] == 0
    assert result['pending_recovered'] == 0
    # No tasks should be scheduled
    assert mock_schedule.call_count == 0
