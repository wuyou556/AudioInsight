from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.database import AsyncSessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for the FastAPI application."""
    # Startup
    print("Starting AudioInsight service...")
    yield
    # Shutdown
    print("Shutting down AudioInsight service...")


app = FastAPI(
    title="AudioInsight",
    description="Audio transcription and summarization service",
    version="0.1.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
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
