"""Recording upload and management endpoints."""
import os
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Recording, Task
from app.schemas import (
    RecordingUploadResponse,
    RecordingDetailResponse,
    RecordingListResponse,
    RecordingListItem,
    LatestTaskInfo,
    ErrorResponse
)
from app.config import settings
from app.services.task_processor import schedule_task

router = APIRouter(prefix="/v1/recordings", tags=["recordings"])
logger = logging.getLogger(__name__)

# Allowed file extensions and MIME types
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac"}
MIME_TYPE_MAP = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac"
}


@router.get(
    "",
    response_model=RecordingListResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"}
    },
    summary="List recordings with pagination",
    description="Get a paginated list of recordings ordered by creation time (newest first)"
)
async def list_recordings(
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page (max 100)"),
    db: AsyncSession = Depends(get_db)
):
    """
    List recordings with pagination.

    Returns:
    - items: List of recording items with latest task status
    - total: Total number of recordings
    - page: Current page number
    - page_size: Items per page

    Each recording item includes:
    - recording_id: UUID of the recording
    - filename: Original filename
    - file_size: File size in bytes
    - created_at: Creation timestamp
    - latest_status: Status of the latest task (if any)
    """
    # Calculate offset
    offset = (page - 1) * page_size

    # Get total count
    count_result = await db.execute(
        select(func.count(Recording.id))
    )
    total = count_result.scalar()

    # Get recordings ordered by created_at DESC (uses idx_recordings_created_at)
    recordings_result = await db.execute(
        select(Recording)
        .order_by(Recording.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    recordings = recordings_result.scalars().all()

    # Build response items
    items = []
    for recording in recordings:
        # Get latest task status for this recording
        task_result = await db.execute(
            select(Task.status)
            .where(Task.recording_id == recording.id)
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        latest_status = task_result.scalar_one_or_none()

        items.append(RecordingListItem(
            recording_id=recording.id,
            filename=recording.filename,
            file_size=recording.file_size,
            created_at=recording.created_at,
            latest_status=latest_status
        ))

    return RecordingListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post(
    "",
    response_model=RecordingUploadResponse,
    status_code=201,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file"},
    }
)
async def upload_recording(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload an audio file for transcription and summarization.

    - **file**: Audio file (wav/mp3/m4a/aac, max 50MB)

    Returns recording_id, task_id, and status.
    """
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Invalid file extension: {file_ext} for file {file.filename}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_FILE_EXTENSION",
                    "message": f"File extension {file_ext} not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
                    "details": {"allowed_extensions": list(ALLOWED_EXTENSIONS)}
                }
            }
        )

    # Read file content and validate size
    content = await file.read()
    file_size = len(content)

    if file_size > settings.max_file_size:
        logger.warning(f"File too large: {file_size} bytes for file {file.filename}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": f"File size {file_size} bytes exceeds maximum {settings.max_file_size} bytes (50MB)",
                    "details": {
                        "file_size": file_size,
                        "max_size": settings.max_file_size
                    }
                }
            }
        )

    # Create uploads directory if not exists
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_id = uuid.uuid4()
    saved_filename = f"{file_id}{file_ext}"
    file_path = upload_dir / saved_filename

    # Store relative path for database
    relative_path = f"{settings.upload_dir}/{saved_filename}"

    # Save file to disk
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save file {saved_filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "FILE_SAVE_ERROR",
                    "message": "Failed to save uploaded file",
                    "details": {"error": str(e)}
                }
            }
        )

    # Determine MIME type
    mime_type = MIME_TYPE_MAP.get(file_ext, "application/octet-stream")

    # Create Recording record
    recording = Recording(
        id=file_id,
        filename=file.filename,
        file_path=relative_path,
        file_size=file_size,
        mime_type=mime_type,
        file_hash=str(file_id)  # Temporary: use UUID as hash, real hash implementation in future issue
    )

    # Create Task record
    task = Task(
        recording_id=recording.id,
        status="pending"
    )

    # Save to database
    try:
        db.add(recording)
        db.add(task)
        await db.commit()
        await db.refresh(recording)
        await db.refresh(task)
    except Exception as e:
        # Rollback database and delete file
        await db.rollback()
        try:
            os.remove(file_path)
        except Exception:
            pass
        logger.error(f"Database error while saving recording: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DATABASE_ERROR",
                    "message": "Failed to save recording to database",
                    "details": {"error": str(e)}
                }
            }
        )

    logger.info(
        f"Recording uploaded: recording_id={recording.id}, "
        f"filename={file.filename}, file_size={file_size}"
    )

    # P2-5: Schedule background task processing with error handling
    try:
        schedule_task(task.id)
    except Exception as e:
        # Log scheduling error but don't fail the upload
        # The upload succeeded, task can be retried manually
        logger.error(f"Failed to schedule task {task.id}: {e}")

    return RecordingUploadResponse(
        recording_id=recording.id,
        task_id=task.id,
        status=task.status,
        is_duplicate=False
    )


@router.get(
    "/{recording_id}",
    response_model=RecordingDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Recording not found"}
    },
    summary="Get recording details",
    description="Retrieve recording metadata and latest task information"
)
async def get_recording_detail(
    recording_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get recording details by ID.

    Returns recording information including:
    - recording_id: UUID of the recording
    - filename: Original filename
    - file_size: File size in bytes
    - created_at: Recording creation timestamp
    - latest_task: Latest task info (if any)
      - task_id: UUID of the task
      - status: Current status
      - transcript: Transcribed text (only if status=done)
      - summary: Summary JSON (only if status=done)
    """
    # Query recording
    result = await db.execute(
        select(Recording).where(Recording.id == recording_id)
    )
    recording = result.scalar_one_or_none()

    if not recording:
        logger.warning(f"Recording {recording_id} not found")
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "RECORDING_NOT_FOUND",
                    "message": f"Recording {recording_id} not found",
                    "details": {}
                }
            }
        )

    # Query latest task for this recording
    task_result = await db.execute(
        select(Task)
        .where(Task.recording_id == recording_id)
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    latest_task = task_result.scalar_one_or_none()

    # Build latest_task info
    latest_task_info = None
    if latest_task:
        latest_task_info = LatestTaskInfo(
            task_id=latest_task.id,
            status=latest_task.status,
            transcript=latest_task.transcript if latest_task.status == "done" else None,
            summary=latest_task.summary_json if latest_task.status == "done" else None
        )

    return RecordingDetailResponse(
        recording_id=recording.id,
        filename=recording.filename,
        file_size=recording.file_size,
        created_at=recording.created_at,
        latest_task=latest_task_info
    )

