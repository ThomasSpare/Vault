from fastapi import FastAPI
from app.api.endpoints import upload
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

# Include routers
app.include_router(upload.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Content Vault API"}