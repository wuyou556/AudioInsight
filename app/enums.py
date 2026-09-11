"""Enums for the application."""
from enum import Enum


class TaskStatus(str, Enum):
    """Task processing status."""
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    DONE = "done"
    FAILED = "failed"
