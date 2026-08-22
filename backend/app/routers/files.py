from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
import os

from ..auth import get_current_user
from ..models import User
from ..services.storage import StorageError, get_storage, safe_name

router = APIRouter(prefix="/api", tags=["files"])

# Max size for a source file. Keeps a stray 2GB upload from eating Render's RAM.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))

ALLOWED_SUFFIXES = (".py",)
ALLOWED_EXACT = ("requirements.txt",)


def _check_allowed(filename: str) -> None:
    if not (filename.endswith(ALLOWED_SUFFIXES) or filename in ALLOWED_EXACT):
        raise HTTPException(
            status_code=400,
            detail="Only Python files (.py) and requirements.txt are allowed",
        )


def _handle(exc: Exception) -> HTTPException:
    """Translate storage-layer errors into sensible HTTP responses."""
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail="File not found")
    if isinstance(exc, StorageError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Storage backend error: {exc}")


# NOTE: files are namespaced per user by the storage layer, so two users can
# each own a main.py without clobbering each other. Every handler below passes
# current_user.username — never a client-supplied username.


@router.get("/files")
async def list_files(current_user: User = Depends(get_current_user)):
    """List the current user's files."""
    try:
        files = get_storage().list_files(current_user.username)
        # Keep the original response shape so the frontend needs no changes.
        return {"files": [f["filename"] for f in files], "details": files}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a Python file into the current user's folder."""
    filename = safe_name(file.filename or "")
    _check_allowed(filename)

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (limit {MAX_UPLOAD_BYTES // 1024} KB)",
        )

    try:
        get_storage().write_file(current_user.username, filename, content)
        return {"filename": filename, "message": "File uploaded successfully"}
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/view/{filename}")
async def view_file(filename: str, current_user: User = Depends(get_current_user)):
    """Return a file's text content for the editor."""
    try:
        content = get_storage().read_file(current_user.username, filename)
        return {
            "filename": safe_name(filename),
            "content": content.decode("utf-8", errors="replace"),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.put("/edit/{filename}")
async def edit_file(
    filename: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Save edited content back to storage."""
    name = safe_name(filename)
    _check_allowed(name)

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    storage = get_storage()
    try:
        if not storage.file_exists(current_user.username, name):
            raise HTTPException(status_code=404, detail="File not found")
        storage.write_file(current_user.username, name, content)
        return {"message": "File saved successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        raise _handle(exc) from exc


@router.delete("/files/{filename}")
async def delete_file(filename: str, current_user: User = Depends(get_current_user)):
    """Delete one of the current user's files."""
    try:
        get_storage().delete_file(current_user.username, filename)
        return {"message": f"File {safe_name(filename)} deleted successfully"}
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/download/{filename}")
async def download_file(filename: str, current_user: User = Depends(get_current_user)):
    """Download a file. Streams from storage rather than the local disk."""
    name = safe_name(filename)
    try:
        content = get_storage().read_file(current_user.username, name)
    except Exception as exc:
        raise _handle(exc) from exc

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/create/{filename}")
async def create_file(filename: str, current_user: User = Depends(get_current_user)):
    """Create a new empty Python file."""
    name = safe_name(filename)
    if not name.endswith(".py"):
        raise HTTPException(status_code=400, detail="Filename must end with .py")

    storage = get_storage()
    try:
        if storage.file_exists(current_user.username, name):
            raise HTTPException(status_code=400, detail="File already exists")
        storage.write_file(current_user.username, name, b"# Created by NEBULA\n\n")
        return {"message": f"File {name} created successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        raise _handle(exc) from exc


@router.put("/rename/{filename}")
async def rename_file(
    filename: str,
    new_name: str,
    current_user: User = Depends(get_current_user),
):
    """Rename one of the current user's files."""
    target = safe_name(new_name)
    if not target.endswith(".py"):
        raise HTTPException(status_code=400, detail="New filename must end with .py")

    storage = get_storage()
    try:
        if storage.file_exists(current_user.username, target):
            raise HTTPException(status_code=400, detail="File already exists")
        storage.rename_file(current_user.username, filename, target)
        return {"message": f"File renamed to {target}"}
    except HTTPException:
        raise
    except Exception as exc:
        raise _handle(exc) from exc
