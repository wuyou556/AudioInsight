"""Task processor for handling background transcription and summarization."""
import asyncio
import logging
import os
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Task
from app.services.transcription import mock_transcribe

logger = logging.getLogger(__name__)

# Background task registry to keep track of running tasks
_background_tasks = set()


async def process_task(task_id: UUID):
    """
    Process a single task: transcription.

    Args:
        task_id: UUID of the task to process
    """
    task = None  # P0-1: Initialize to avoid unbound variable in exception handler
    async with AsyncSessionLocal() as db:
        try:
            # P2-6: Get task and recording with eager loading (avoid N+1 query)
            result = await db.execute(
                select(Task)
                .options(selectinload(Task.recording))
                .where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                logger.error(f"Task {task_id} not found")
                return

            # P0-3: Check if recording exists after refresh
            if not task.recording:
                logger.error(f"Task {task_id}: Recording not found or deleted")
                task.status = "failed"
                task.error_message = "Recording not found or deleted"
                await db.commit()
                return

            file_path = task.recording.file_path

            # P2-8: Verify file exists on disk before processing
            if not os.path.exists(file_path):
                logger.error(f"Task {task_id}: File not found on disk: {file_path}")
                task.status = "failed"
                task.error_message = f"Audio file not found: {file_path}"
                await db.commit()
                return

            # Update status to transcribing
            task.status = "transcribing"
            await db.commit()
            logger.info(f"Task {task_id} started transcribing")

            # Perform mock transcription
            try:
                transcript = await mock_transcribe(file_path)

                # P1: Save transcript and update status to done (include commit in try)
                task.transcript = transcript
                task.status = "done"
                task.error_message = None
                await db.commit()
                logger.info(f"Task {task_id} completed successfully")

            except Exception as e:
                # P1: Transcription or commit failed
                task.status = "failed"
                task.error_message = str(e)
                await db.commit()
                logger.error(f"Task {task_id} failed: {e}")

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            # Try to mark task as failed
            try:
                if task:
                    task.status = "failed"
                    task.error_message = f"Processing error: {str(e)}"
                    await db.commit()
            except Exception as ex:
                # Log the failure to update status
                logger.error(f"Failed to mark task {task_id} as failed: {ex}")



def schedule_task(task_id: UUID):
    """
    Schedule a task for background processing.

    Args:
        task_id: UUID of the task to schedule
    """
    task = asyncio.create_task(process_task(task_id))

    # Keep a reference to prevent garbage collection
    _background_tasks.add(task)
    # P0-2: Fix callback signature - discard expects the asyncio.Task object
    task.add_done_callback(lambda t: _background_tasks.discard(t))

    logger.info(f"Task {task_id} scheduled for processing")
