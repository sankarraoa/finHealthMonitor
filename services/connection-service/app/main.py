"""FastAPI application for Connection Service microservice."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import logging

from app.config import config
from app.routes import connections
from app.database import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Connection Service",
    description="OAuth connection management microservice for FinHealthMonitor",
    version="1.0.0"
)

# Include routers
app.include_router(connections.router)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info(f"Starting {config.SERVICE_NAME}...")
    init_db()


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": "1.0.0"
    })


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": config.SERVICE_NAME,
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("PORT", config.PORT))
    host = os.getenv("HOST", config.HOST)
    
    logger.info(f"Starting {config.SERVICE_NAME} on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
