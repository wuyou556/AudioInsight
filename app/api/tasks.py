"""API endpoints for task operations."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Task
from app.schemas import TaskStatusResponse, ErrorResponse

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
    # Query task
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        logger.warning(f"Task {task_id} not found")
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"Task {task_id} not found",
                    "details": {}
                }
            }
        )

    return TaskStatusResponse(
        task_id=task.id,
        recording_id=task.recording_id,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at
    )
