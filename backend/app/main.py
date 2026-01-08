"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="RESTful API for Kingdom Auto Finance accounting system",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """
    Root endpoint - health check.
    """
    return {
        "message": "Kingdom Auto Finance API",
        "version": settings.VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy"}


# Include API routers
from app.api import payments, reports, amortization, jobs

app.include_router(
    payments.router,
    prefix=f"{settings.API_V1_PREFIX}/payments",
    tags=["payments"]
)

app.include_router(
    reports.router,
    prefix=f"{settings.API_V1_PREFIX}/reports",
    tags=["reports"]
)

app.include_router(
    amortization.router,
    prefix=f"{settings.API_V1_PREFIX}/amortization",
    tags=["amortization"]
)

app.include_router(
    jobs.router,
    prefix=f"{settings.API_V1_PREFIX}/jobs",
    tags=["jobs"]
)
