"""Common utility functions for API endpoints."""
from uuid import UUID
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


def raise_not_found(entity_type: str, entity_id: UUID):
    """
    Raise a 404 HTTPException with standardized error format.

    Args:
        entity_type: Type of entity (e.g., "Task", "Recording")
        entity_id: UUID of the entity that was not found

    Raises:
        HTTPException: 404 error with structured detail
    """
    error_code = f"{entity_type.upper()}_NOT_FOUND"
    message = f"{entity_type} {entity_id} not found"

    logger.warning(message)

    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": error_code,
                "message": message,
                "details": {}
            }
        }
    )


async def get_or_404(db, model, entity_id: UUID, entity_type: str):
    """
    Get an entity by ID or raise 404 if not found.

    Args:
        db: Database session
        model: SQLAlchemy model class
        entity_id: UUID of the entity
        entity_type: Type name for error message

    Returns:
        The entity instance

    Raises:
        HTTPException: 404 if entity not found
    """
    from sqlalchemy import select

    result = await db.execute(
        select(model).where(model.id == entity_id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise_not_found(entity_type, entity_id)

    return entity
