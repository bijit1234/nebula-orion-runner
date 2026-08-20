from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import shutil
from typing import List
from .. import database, auth
from ..auth import get_current_user
from ..models import User

router = APIRouter(prefix="/api", tags=["files"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
UPLOAD_DIR_ABS = os.path.abspath(UPLOAD_DIR)


def safe_file_path(filename: str) -> str:
    """
    Resolve `filename` inside UPLOAD_DIR and reject any path that
    escapes it (e.g. '../../etc/passwd', absolute paths, etc).
    """
    # Strip any directory components the client tried to sneak in
    # (handles both '/' and '\' separators, and leading '..').
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    candidate = os.path.abspath(os.path.join(UPLOAD_DIR_ABS, safe_name))

    # Belt-and-suspenders: make sure the resolved path is still inside UPLOAD_DIR
    if os.path.commonpath([candidate, UPLOAD_DIR_ABS]) != UPLOAD_DIR_ABS:
        raise HTTPException(status_code=400, detail="Invalid filename")

    return candidate

@router.get("/files")
async def list_files(current_user: User = Depends(get_current_user)):
    """List all uploaded files"""
    try:
        files = []
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                files.append({
                    "filename": filename,
                    "size": stat.st_size,
                    "last_modified": stat.st_mtime
                })
        return {"files": [f["filename"] for f in files]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a Python file"""
    if not file.filename.endswith('.py') and file.filename != 'requirements.txt':
        raise HTTPException(
            status_code=400,
            detail="Only Python files (.py) and requirements.txt are allowed"
        )
    
    file_path = safe_file_path(file.filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": os.path.basename(file_path), "message": "File uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/view/{filename}")
async def view_file(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """View file content"""
    file_path = safe_file_path(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(file_path, "r") as f:
            content = f.read()
        return {"filename": filename, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/edit/{filename}")
async def edit_file(
    filename: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Edit/save file content"""
    file_path = safe_file_path(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"message": "File saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/files/{filename}")
async def delete_file(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a file"""
    file_path = safe_file_path(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        os.remove(file_path)
        return {"message": f"File {filename} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
async def download_file(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Download a file"""
    file_path = safe_file_path(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path, filename=os.path.basename(file_path))

@router.post("/create/{filename}")
async def create_file(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Create a new Python file"""
    if not filename.endswith('.py'):
        raise HTTPException(status_code=400, detail="Filename must end with .py")
    
    file_path = safe_file_path(filename)
    if os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        with open(file_path, "w") as f:
            f.write("# Created by NEBULA\n\n")
        return {"message": f"File {filename} created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/rename/{filename}")
async def rename_file(
    filename: str,
    new_name: str,
    current_user: User = Depends(get_current_user)
):
    """Rename a file"""
    if not new_name.endswith('.py'):
        raise HTTPException(status_code=400, detail="New filename must end with .py")
    
    old_path = safe_file_path(filename)
    new_path = safe_file_path(new_name)
    
    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="File not found")
    if os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        os.rename(old_path, new_path)
        return {"message": f"File renamed to {new_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))