from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.api import recordings, tasks
from app.services.task_processor import recover_tasks_on_startup


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

    # Recover incomplete tasks from previous run in background
    # Use asyncio.create_task to avoid blocking server startup
    asyncio.create_task(_recover_tasks_with_timeout())

    yield
    # Shutdown
    logger.info("Shutting down AudioInsight service...")


async def _recover_tasks_with_timeout():
    """
    Wrapper to run task recovery with a timeout.

    Runs in background to avoid blocking server startup.
    """
    try:
        # Set reasonable timeout (30 seconds)
        await asyncio.wait_for(
            recover_tasks_on_startup(),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error(
            "Task recovery timed out after 30 seconds. "
            "Server started but some tasks may not have been recovered."
        )
    except Exception as e:
        logger.error(f"Task recovery failed: {e}", exc_info=True)


app = FastAPI(
    title="AudioInsight",
    description="Audio transcription and summarization service",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
