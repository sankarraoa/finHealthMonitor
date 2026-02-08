"""FastAPI application for User Service microservice."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import logging

from app.config import config
from app.routes import auth, users, tenants, roles, permissions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="User Service",
    description="User management microservice for FinHealthMonitor",
    version="1.0.0"
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tenants.router)
app.include_router(roles.router)
app.include_router(permissions.router)


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
