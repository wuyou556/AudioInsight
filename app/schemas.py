"""Pydantic schemas for request/response models."""
from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field


# Error response schemas
class ErrorDetail(BaseModel):
    """Error detail structure."""
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: ErrorDetail


# Recording schemas
class RecordingUploadResponse(BaseModel):
    """Response for recording upload."""
    recording_id: UUID
    task_id: UUID
    status: str
    is_duplicate: bool = False

    class Config:
        from_attributes = True


class RecordingDetail(BaseModel):
    """Recording detail with task information."""
    id: UUID
    filename: str
    file_path: str
    file_size: int
    mime_type: str
    created_at: datetime
    updated_at: datetime
    latest_task: Optional["TaskDetail"] = None

    class Config:
        from_attributes = True


# Task schemas
class TaskDetail(BaseModel):
    """Task detail."""
    id: UUID
    recording_id: UUID
    status: str
    transcript: Optional[str] = None
    summary_json: Optional[dict] = None
    error_message: Optional[str] = None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskStatusResponse(BaseModel):
    """Response for GET /v1/tasks/{id}."""
    task_id: UUID
    recording_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskRetryResponse(BaseModel):
    """Response for POST /v1/tasks/{id}/retry."""
    task_id: UUID
    recording_id: UUID
    status: str
    retry_count: int
    updated_at: datetime

    class Config:
        from_attributes = True


class LatestTaskInfo(BaseModel):
    """Latest task information for recording detail."""
    task_id: UUID
    status: str
    transcript: Optional[str] = None
    summary: Optional[dict] = None

    class Config:
        from_attributes = True


class RecordingDetailResponse(BaseModel):
    """Response for GET /v1/recordings/{id}."""
    recording_id: UUID
    filename: str
    file_size: int
    created_at: datetime
    latest_task: Optional[LatestTaskInfo] = None

    class Config:
        from_attributes = True


class RecordingListItem(BaseModel):
    """Recording list item with latest task status."""
    recording_id: UUID
    filename: str
    file_size: int
    created_at: datetime
    latest_status: Optional[str] = None

    class Config:
        from_attributes = True


class RecordingListResponse(BaseModel):
    """Response for GET /v1/recordings with pagination."""
    items: list[RecordingListItem]
    total: int
    page: int
    page_size: int
