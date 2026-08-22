import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import database, models
from ..auth import get_current_user
from ..models import User
from ..runner import runner
from ..services.storage import StorageError, get_storage, safe_name, safe_user

router = APIRouter(prefix="/api", tags=["execution"])


def run_key(username: str, filename: str) -> str:
    """
    Tracking key for the runner. Namespacing by user means alice's main.py and
    bob's main.py are separate executions rather than fighting over one slot.
    """
    return f"{safe_user(username)}/{safe_name(filename)}"


@router.post("/run/{filename}")
async def run_file(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Fetch the file from storage into a local workspace, then execute it."""
    name = safe_name(filename)
    key = run_key(current_user.username, name)
    storage = get_storage()

    try:
        if not storage.file_exists(current_user.username, name):
            raise HTTPException(status_code=404, detail=f"File not found: {name}")
        # For the FileCloud backend this downloads the user's files to local
        # disk, because a subprocess can only execute something real.
        workspace = storage.materialize_dir(current_user.username)
    except HTTPException:
        raise
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc

    abs_path = os.path.join(workspace, name)
    if not os.path.exists(abs_path):
        raise HTTPException(
            status_code=502,
            detail=f"Could not stage '{name}' from storage for execution",
        )
    if os.path.getsize(abs_path) == 0:
        raise HTTPException(status_code=400, detail=f"File '{name}' is empty.")

    if runner.running_files.get(key):
        raise HTTPException(status_code=400, detail=f"File '{name}' is already running")

    result = runner.run_file(name, workspace, key=key)

    if "error" in result:
        db.add(
            models.ExecutionHistory(
                user_id=current_user.id,
                filename=name,
                status="Error",
                error=result["error"],
                return_code=-1,
            )
        )
        db.commit()
        raise HTTPException(status_code=400, detail=result["error"])

    # Return the clean filename so the frontend polls with the right key.
    result["filename"] = name
    return result


@router.post("/stop")
async def stop_file(current_user: User = Depends(get_current_user)):
    """Stop whatever the current user is running (never another user's job)."""
    prefix = f"{safe_user(current_user.username)}/"
    mine = runner.running_keys(prefix=prefix)
    if not mine:
        raise HTTPException(status_code=400, detail="No file is currently running")

    result = runner.stop_file(mine[0])
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/result/{filename}")
async def get_result(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Poll for the result of the current user's execution."""
    name = safe_name(filename)
    key = run_key(current_user.username, name)

    if key not in runner.processes and key not in runner.results:
        raise HTTPException(
            status_code=404, detail=f"File '{name}' not found or not running"
        )

    result = runner.get_result(key)

    # Save history exactly once, not on every poll.
    if result.get("finished") and not result.get("history_saved"):
        db.add(
            models.ExecutionHistory(
                user_id=current_user.id,
                filename=name,
                status=result.get("status", "Finished"),
                output=result.get("output", ""),
                error=result.get("error", ""),
                return_code=result.get("return_code", 0),
                execution_time=result.get("execution_time", 0),
                memory_usage=result.get("memory_usage", 0),
            )
        )
        db.commit()
        result["history_saved"] = True

    return {k: v for k, v in result.items() if k != "history_saved"}


@router.get("/debug/runner")
async def debug_runner(current_user: User = Depends(get_current_user)):
    """Runner state for the current user only."""
    prefix = f"{safe_user(current_user.username)}/"
    return {
        "processes": [k for k in runner.processes if k.startswith(prefix)],
        "running": runner.running_keys(prefix=prefix),
        "storage_backend": get_storage().name,
    }
