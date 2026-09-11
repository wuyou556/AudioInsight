"""API endpoints for task operations."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Task
from app.schemas import TaskStatusResponse, ErrorResponse
from app.api.utils import get_or_404

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
