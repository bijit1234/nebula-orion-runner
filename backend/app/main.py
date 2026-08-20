from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import database
from .routers import files, execution, history
from .auth import router as auth_router
import os
from dotenv import load_dotenv

load_dotenv()

# Create database tables
database.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="NEBULA Code Runner API",
    description="Cloud-based Python code execution API",
    version="1.0.0"
)

# CORS — read allowed origins from env so it works in both dev and cloud
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(files.router)
app.include_router(execution.router)
app.include_router(history.router)

@app.get("/")
async def root():
    return {
        "name": "NEBULA Code Runner API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # reload=True is dev-only — the Dockerfile uses uvicorn directly without reload
    debug = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=debug
    )