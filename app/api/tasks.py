"""API endpoints for task operations."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Task
from app.schemas import TaskStatusResponse, TaskRetryResponse, ErrorResponse
from app.api.utils import get_or_404
from app.services.task_processor import schedule_task
from app.enums import TaskStatus

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"}
    },
    summary="Get task status",
    description="Retrieve the current status and timestamps of a task"
)
async def get_task_status(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get task status by ID.

    Returns task details including:
    - task_id: UUID of the task
    - recording_id: Associated recording UUID
    - status: Current status (pending/transcribing/summarizing/done/failed)
    - created_at: Task creation timestamp
    - updated_at: Last update timestamp
    """
    # Use utility function for get-or-404 pattern
    task = await get_or_404(db, Task, task_id, "Task")

    return TaskStatusResponse(
        task_id=task.id,
        recording_id=task.recording_id,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.post(
    "/{task_id}/retry",
    response_model=TaskRetryResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"},
        409: {"model": ErrorResponse, "description": "Task not in failed state"}
    },
    summary="Retry failed task",
    description="Manually retry a failed task by resetting it to pending and rescheduling"
)
async def retry_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retry a failed task.

    Only tasks in 'failed' status can be retried. The task will be:
    - Reset to 'pending' status
    - Increment retry_count
    - Rescheduled for processing

    Returns:
    - task_id: UUID of the task
    - recording_id: Associated recording UUID
    - status: New status (pending)
    - retry_count: Updated retry count
    - updated_at: Update timestamp
    """
    # Get task or 404
    task = await get_or_404(db, Task, task_id, "Task")

    # Check if task is in failed state
    if task.status != TaskStatus.FAILED.value:
        logger.warning(f"Task {task_id} retry attempted but status is {task.status}")
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "TASK_NOT_FAILED",
                    "message": "Only failed tasks can be retried",
                    "details": {"current_status": task.status}
                }
            }
        )

    # Reset task state
    task.status = TaskStatus.PENDING.value
    task.retry_count += 1
    task.error_message = None

    await db.commit()
    await db.refresh(task)

    logger.info(f"Task {task_id} manually retried, retry_count: {task.retry_count}")

    # Reschedule task processing
    try:
        schedule_task(task_id)
    except Exception as e:
        logger.error(f"Failed to schedule task {task_id} for retry: {e}")
        # Note: We don't fail the request since the task state was updated
        # The task can be retried again or processed manually

    return TaskRetryResponse(
        task_id=task.id,
        recording_id=task.recording_id,
        status=task.status,
        retry_count=task.retry_count,
        updated_at=task.updated_at
    )
