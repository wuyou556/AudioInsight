"""Task processor for handling background transcription and summarization."""
import asyncio
import logging
from uuid import UUID
from sqlalchemy import select
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
    async with AsyncSessionLocal() as db:
        try:
            # Get task and recording
            result = await db.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                logger.error(f"Task {task_id} not found")
                return

            # Get recording file path
            await db.refresh(task, ["recording"])
            file_path = task.recording.file_path

            # Update status to transcribing
            task.status = "transcribing"
            await db.commit()
            logger.info(f"Task {task_id} started transcribing")

            # Perform mock transcription
            try:
                transcript = await mock_transcribe(file_path)

                # Save transcript and update status to done
                task.transcript = transcript
                task.status = "done"
                task.error_message = None
                await db.commit()
                logger.info(f"Task {task_id} completed successfully")

            except Exception as e:
                # Transcription failed
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
            except Exception:
                pass


def schedule_task(task_id: UUID):
    """
    Schedule a task for background processing.

    Args:
        task_id: UUID of the task to schedule
    """
    task = asyncio.create_task(process_task(task_id))

    # Keep a reference to prevent garbage collection
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    logger.info(f"Task {task_id} scheduled for processing")
