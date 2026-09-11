"""Recording upload and management endpoints."""
import os
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Recording, Task
from app.schemas import RecordingUploadResponse, ErrorResponse
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

    # Schedule background task processing
    schedule_task(task.id)

    return RecordingUploadResponse(
        recording_id=recording.id,
        task_id=task.id,
        status=task.status,
        is_duplicate=False
    )
