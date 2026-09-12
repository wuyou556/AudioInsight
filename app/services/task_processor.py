"""Task processor for handling background transcription and summarization."""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Task
from app.services.transcription import mock_transcribe
from app.services.summarization import llm_summarize
from app.config import settings

logger = logging.getLogger(__name__)

# Background task registry to keep track of running tasks
_background_tasks = set()

# Global semaphore for concurrency control
_semaphore = None


def _get_semaphore() -> asyncio.Semaphore:
    """Get or create the global semaphore for task concurrency control.

    Creates a new semaphore if none exists or if the current one is bound
    to a different event loop (common in testing scenarios).
    """
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_tasks)
        logger.debug(f"Created new semaphore with limit {settings.max_concurrent_tasks}")
    return _semaphore


def _reset_semaphore_for_testing():
    """Reset the global semaphore. Only for testing purposes."""
    global _semaphore
    _semaphore = None


async def _update_task_status(
    task: Task,
    db: AsyncSession,
    status: str,
    log_message: str,
    error_message: str = None
):
    """
    Helper function to update task status and log.

    Args:
        task: Task to update
        db: Database session
        status: New status value
        log_message: Message to log
        error_message: Optional error message to save
    """
    task.status = status
    if error_message:
        task.error_message = error_message
    await db.commit()

    if status == "failed":
        logger.error(log_message)
    else:
        logger.info(log_message)


async def process_task(task_id: UUID):
    """
    Process a single task: transcription and summarization.

    Raises exceptions for transient failures that should be retried.
    Returns normally for permanent failures (file not found, task not found).

    Args:
        task_id: UUID of the task to process

    Raises:
        Exception: For transient errors that should be retried
    """
    task = None
    async with AsyncSessionLocal() as db:
        # Get task and recording with eager loading
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.recording))
            .where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            logger.error(f"Task {task_id} not found")
            return  # Permanent failure - don't retry

        # Check if recording exists
        if not task.recording:
            await _update_task_status(
                task, db, "failed",
                f"Task {task_id}: Recording not found or deleted",
                "Recording not found or deleted"
            )
            return  # Permanent failure - don't retry

        file_path = task.recording.file_path

        # Verify file exists on disk
        if not os.path.exists(file_path):
            await _update_task_status(
                task, db, "failed",
                f"Task {task_id}: File not found on disk: {file_path}",
                f"Audio file not found: {file_path}"
            )
            return  # Permanent failure - don't retry

        # Update status to transcribing
        await _update_task_status(
            task, db, "transcribing",
            f"Task {task_id} started transcribing"
        )

        # Perform transcription - let exceptions propagate for retry
        transcript = await mock_transcribe(file_path)

        # Save transcript
        task.transcript = transcript
        await db.commit()
        logger.info(f"Task {task_id} transcription completed")

        # Update status to summarizing
        await _update_task_status(
            task, db, "summarizing",
            f"Task {task_id} started summarizing"
        )

        # Perform LLM summarization - let exceptions propagate for retry
        summary_result = await llm_summarize(transcript)

        # Save summary and update status to done
        task.summary_json = summary_result
        task.status = "done"
        task.error_message = None
        await db.commit()
        logger.info(f"Task {task_id} completed successfully")



async def process_task_with_retry(task_id: UUID):
    """
    Process a task with automatic retry logic.

    Retries up to MAX_RETRIES times with exponential backoff (1s, 2s, 4s).
    Only marks task as failed after all retries are exhausted.

    Args:
        task_id: UUID of the task to process
    """
    max_retries = settings.max_retries

    for attempt in range(max_retries + 1):  # Initial attempt + retries
        try:
            await process_task(task_id)
            # Success - no need to retry
            return

        except Exception as e:
            # Check if task still exists and update retry count
            async with AsyncSessionLocal() as db:
                try:
                    result = await db.execute(
                        select(Task).where(Task.id == task_id)
                    )
                    task = result.scalar_one_or_none()

                    if not task:
                        # Task was deleted - abort retry
                        logger.warning(
                            f"Task {task_id} not found in database, aborting retry"
                        )
                        return

                    if attempt < max_retries:
                        # Not the last attempt - increment retry count and retry
                        task.retry_count = attempt + 1
                        await db.commit()

                        delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.info(
                            f"Task {task_id} retry attempt {attempt + 1}/{max_retries} "
                            f"after {delay}s delay (error: {str(e)[:100]})"
                        )
                        await asyncio.sleep(delay)

                    else:
                        # Last attempt failed - mark as failed
                        task.retry_count = max_retries
                        task.status = "failed"
                        # Preserve original error message if it's more specific
                        if not task.error_message:
                            task.error_message = f"All retries exhausted: {str(e)}"
                        await db.commit()
                        logger.error(
                            f"Task {task_id} failed after {max_retries} retries: {e}"
                        )
                        return

                except Exception as db_error:
                    logger.error(
                        f"Failed to update retry count for task {task_id}: {db_error}"
                    )
                    # Don't continue retry loop if we can't update the database
                    return


async def process_task_with_semaphore(task_id: UUID):
    """
    Wrapper that enforces semaphore-based concurrency control.

    Args:
        task_id: UUID of the task to process
    """
    semaphore = _get_semaphore()

    logger.info(f"Task {task_id} waiting for processing slot")
    async with semaphore:
        logger.info(f"Task {task_id} acquired processing slot")
        await process_task_with_retry(task_id)


def schedule_task(task_id: UUID):
    """
    Schedule a task for background processing with retry and concurrency control.

    Args:
        task_id: UUID of the task to schedule
    """
    task = asyncio.create_task(process_task_with_semaphore(task_id))

    # Keep a reference to prevent garbage collection
    _background_tasks.add(task)
    # P0-2: Fix callback signature - discard expects the asyncio.Task object
    task.add_done_callback(lambda t: _background_tasks.discard(t))

    logger.info(f"Task {task_id} scheduled for processing")


async def recover_tasks_on_startup() -> dict:
    """
    Recover incomplete tasks on service startup.

    Resets all interrupted tasks (in processing states) to pending,
    then reschedules all pending tasks. Service restart means all
    processing workers are gone, so all in-progress tasks need to restart.

    Returns:
        dict: Statistics about recovered tasks
            - interrupted_reset: number of interrupted tasks reset to pending
            - pending_recovered: number of pending tasks rescheduled
    """
    interrupted_reset = 0
    pending_recovered = 0

    try:
        async with AsyncSessionLocal() as db:
            # Find all interrupted tasks (in processing states)
            # Service restart means these workers no longer exist
            interrupted_query = select(Task).where(
                Task.status.in_(['transcribing', 'summarizing'])
            )
            interrupted_result = await db.execute(interrupted_query)
            interrupted_tasks = interrupted_result.scalars().all()

            # Reset interrupted tasks to pending
            for task in interrupted_tasks:
                old_status = task.status
                old_updated_at = task.updated_at

                task.status = "pending"
                task.retry_count = 0  # Reset retry count for fresh start
                task.error_message = None  # Clear old error messages
                # Don't manually set updated_at - let SQLAlchemy's onupdate handle it

                interrupted_reset += 1
                logger.warning(
                    f"Reset interrupted task {task.id} from {old_status} state "
                    f"(last updated: {old_updated_at})"
                )

            if interrupted_reset > 0:
                try:
                    await db.commit()
                    logger.info(f"Reset {interrupted_reset} interrupted tasks to pending")
                except Exception as commit_error:
                    logger.error(f"Failed to commit interrupted task resets: {commit_error}")
                    await db.rollback()
                    # Reset counter since commit failed
                    interrupted_reset = 0
                    # Don't continue to scheduling if reset failed
                    return {
                        'interrupted_reset': 0,
                        'pending_recovered': 0
                    }

        # Use a fresh session for querying pending tasks
        async with AsyncSessionLocal() as db:
            # Find all pending tasks, but only load their IDs
            # Limit to reasonable batch size to avoid memory issues
            BATCH_LIMIT = 1000
            pending_query = (
                select(Task.id)
                .where(Task.status == 'pending')
                .limit(BATCH_LIMIT)
            )
            pending_result = await db.execute(pending_query)
            pending_task_ids = pending_result.scalars().all()

            # Schedule all pending tasks
            for task_id in pending_task_ids:
                schedule_task(task_id)
                pending_recovered += 1

            if pending_recovered >= BATCH_LIMIT:
                logger.warning(
                    f"Reached batch limit ({BATCH_LIMIT}) for pending task recovery. "
                    "Some tasks may not have been scheduled."
                )

            logger.info(
                f"Task recovery complete: recovered {pending_recovered} pending tasks, "
                f"reset {interrupted_reset} interrupted tasks"
            )

    except Exception as e:
        logger.error(f"Error during task recovery: {e}", exc_info=True)

    return {
        'interrupted_reset': interrupted_reset,
        'pending_recovered': pending_recovered
    }
