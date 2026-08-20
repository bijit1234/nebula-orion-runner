from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import database, auth, models
from ..auth import get_current_user
from ..models import User
from ..runner import runner
from .files import safe_file_path
import os
import time

router = APIRouter(prefix="/api", tags=["execution"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
UPLOAD_DIR = os.path.abspath(UPLOAD_DIR)
print(f"📁 UPLOAD_DIR: {UPLOAD_DIR}")

@router.post("/run/{filename}")
async def run_file(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Run a Python file"""
    # Clean the filename and make sure it can't escape UPLOAD_DIR
    filename = os.path.basename(filename.strip())
    abs_path = safe_file_path(filename)
    
    print(f"🔍 Running file: {filename}")
    print(f"📁 Full path: {abs_path}")
    
    if not os.path.exists(abs_path):
        print(f"❌ File not found: {abs_path}")
        raise HTTPException(
            status_code=404, 
            detail=f"File not found: {filename}"
        )
    
    # Check if file is empty
    if os.path.getsize(abs_path) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"File '{filename}' is empty. Please upload a file with content."
        )
    
    # Check if already running
    if filename in runner.running_files and runner.running_files[filename]:
        raise HTTPException(
            status_code=400,
            detail=f"File '{filename}' is already running"
        )
    
    result = runner.run_file(filename, UPLOAD_DIR)
    
    if "error" in result:
        history = models.ExecutionHistory(
            user_id=current_user.id,
            filename=filename,
            status="Error",
            error=result["error"],
            return_code=-1
        )
        db.add(history)
        db.commit()
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Return the CLEAN filename so the frontend uses the correct key for polling
    result["filename"] = filename
    return result

@router.post("/stop")
async def stop_file(
    current_user: User = Depends(get_current_user)
):
    """Stop the currently running file"""
    # Find the running file
    running_files = [f for f, running in runner.running_files.items() if running]
    if not running_files:
        raise HTTPException(status_code=400, detail="No file is currently running")
    
    filename = running_files[0]
    result = runner.stop_file(filename)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.get("/result/{filename}")
async def get_result(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get the result of a running or completed file"""
    # Always strip any path prefix (e.g. 'workspace/test.py' -> 'test.py')
    filename = os.path.basename(filename.strip())
    print(f"Getting result for: {filename}")
    print(f"Running processes: {list(runner.processes.keys())}")
    print(f"Stored results: {list(runner.results.keys())}")

    # Check both active processes AND stored results
    if filename not in runner.processes and filename not in runner.results:
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found or not running"
        )

    result = runner.get_result(filename)

    # ✅ FIX: Only save history ONCE using a flag — prevents duplicate DB writes on every poll
    if result.get("finished") and not result.get("history_saved"):
        print(f"✅ File finished! Status: {result.get('status')} — saving history")
        history = models.ExecutionHistory(
            user_id=current_user.id,
            filename=filename,
            status=result.get("status", "Finished"),
            output=result.get("output", ""),
            error=result.get("error", ""),
            return_code=result.get("return_code", 0),
            execution_time=result.get("execution_time", 0),
            memory_usage=result.get("memory_usage", 0)
        )
        db.add(history)
        db.commit()
        # Mark so we don't double-save on the next poll
        result["history_saved"] = True
        print(f"✅ History saved for: {filename}")
    elif result.get("finished"):
        print(f"⏭️ History already saved for: {filename}, skipping")
    else:
        print(f"⏳ File still running...")

    # Strip internal tracking flag before returning to frontend
    response = {k: v for k, v in result.items() if k != "history_saved"}
    return response

@router.get("/debug/runner")
async def debug_runner(current_user: User = Depends(get_current_user)):
    """Debug endpoint to see runner state"""
    return {
        "processes": list(runner.processes.keys()),
        "running_files": runner.running_files,
        "start_times": runner.start_times
    }