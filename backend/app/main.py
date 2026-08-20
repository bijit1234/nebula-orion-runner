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

def init_default_admin():
    """
    Seed a default admin user on first startup.
    Only runs when the database has zero users (e.g. fresh cloud deploy).
    Safe to call on every restart — does nothing if users already exist.
    """
    from .models import User
    from .auth import get_password_hash

    db = database.SessionLocal()
    try:
        if db.query(User).count() == 0:
            default_username = os.getenv("ADMIN_USERNAME", "admin")
            default_password = os.getenv("ADMIN_PASSWORD", "password123")
            admin = User(
                username=default_username,
                hashed_password=get_password_hash(default_password)
            )
            db.add(admin)
            db.commit()
            print(f"[NEBULA] Default admin created → username: '{default_username}'")
        else:
            print("[NEBULA] Users already exist — skipping admin seed")
    except Exception as e:
        print(f"[NEBULA] Warning: could not seed admin user: {e}")
    finally:
        db.close()

init_default_admin()

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