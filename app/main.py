from datetime import datetime
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Response
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.api import recordings, tasks

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for the FastAPI application."""
    # Startup
    logger.info("Starting AudioInsight service...")
    yield
    # Shutdown
    logger.info("Shutting down AudioInsight service...")


app = FastAPI(
    title="AudioInsight",
    description="Audio transcription and summarization service",
    version="0.1.0",
    lifespan=lifespan
)

# Register routers
app.include_router(recordings.router)
app.include_router(tasks.router, prefix="/v1/tasks", tags=["tasks"])


@app.get("/health")
async def health_check(response: Response):
    """Health check endpoint that verifies database connectivity."""
    try:
        async with AsyncSessionLocal() as session:
            # Test database connection
            result = await session.execute(text("SELECT 1"))
            result.scalar()

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        response.status_code = 503
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AudioInsight",
        "version": "0.1.0",
        "docs": "/docs"
    }
