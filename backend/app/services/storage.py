"""
Storage abstraction for Nebula user files.

The whole point: the routers never talk to FileCloud directly. They talk to a
StorageBackend. That means when your 15-day FileCloud trial expires you flip
one env var (STORAGE_BACKEND=local) and the app keeps working.

Backends
--------
local      files on the server's disk, under UPLOAD_DIR/<username>/
filecloud  files in a FileCloud tenant, under /<root>/<username>/

Both namespace files per user, so two users can each have their own main.py.

Note on Render: the free tier's disk is EPHEMERAL — anything written by the
'local' backend disappears on every deploy, restart and idle spin-down. Local
is the right choice for development and as a fallback, not for real persistence
on a free Render web service.
"""

from __future__ import annotations

import os
import logging
import shutil
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from .filecloud import FileCloudClient, FileCloudError, filecloud as _filecloud_singleton

log = logging.getLogger("nebula.storage")

UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "./uploads"))
# Where FileCloud-backed files are staged so the code runner can execute them.
WORKSPACE_DIR = os.path.abspath(os.getenv("WORKSPACE_DIR", "./workspace"))

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
# If FileCloud is unreachable at startup, keep serving from local disk instead
# of returning 500s for every request.
FALLBACK_TO_LOCAL = os.getenv("STORAGE_FALLBACK_LOCAL", "true").lower() == "true"


class StorageError(RuntimeError):
    """Backend-agnostic storage failure."""


def safe_name(filename: str) -> str:
    """
    Reduce whatever the client sent to a bare filename.

    Blocks path traversal ('../../etc/passwd'), absolute paths and Windows
    separators. Raises StorageError on anything that isn't a usable name.
    """
    if not filename:
        raise StorageError("Invalid filename")
    candidate = os.path.basename(filename.replace("\\", "/").strip())
    if not candidate or candidate in (".", "..") or candidate.startswith("."):
        raise StorageError("Invalid filename")
    if len(candidate) > 255:
        raise StorageError("Filename too long")
    return candidate


def safe_user(username: str) -> str:
    """Usernames become directory / remote-path components, so sanitise them too."""
    cleaned = "".join(c for c in (username or "") if c.isalnum() or c in "-_.")
    # Leading dots would create hidden dirs (or '..'-lookalikes) on the server
    # and in the FileCloud tree.
    cleaned = cleaned.lstrip(".")
    if not cleaned or cleaned in (".", "..") or len(cleaned) > 64:
        raise StorageError("Invalid username")
    return cleaned


class StorageBackend(ABC):
    """Interface the routers depend on. Keep it small."""

    name: str = "abstract"

    @abstractmethod
    def ensure_user_space(self, username: str) -> None: ...

    @abstractmethod
    def list_files(self, username: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def read_file(self, username: str, filename: str) -> bytes: ...

    @abstractmethod
    def write_file(self, username: str, filename: str, content: bytes) -> None: ...

    @abstractmethod
    def delete_file(self, username: str, filename: str) -> None: ...

    @abstractmethod
    def rename_file(self, username: str, filename: str, new_name: str) -> None: ...

    @abstractmethod
    def file_exists(self, username: str, filename: str) -> bool: ...

    @abstractmethod
    def materialize_dir(self, username: str) -> str:
        """
        Return a LOCAL directory holding this user's files, so the subprocess
        runner can execute them. Local backend returns its own folder; remote
        backends download into a staging dir first.
        """
        ...

    def health(self) -> dict[str, Any]:
        return {"backend": self.name, "ok": True}


class LocalStorage(StorageBackend):
    """Plain filesystem storage, one directory per user."""

    name = "local"

    def __init__(self, root: str = UPLOAD_DIR) -> None:
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _user_dir(self, username: str) -> str:
        path = os.path.join(self.root, safe_user(username))
        os.makedirs(path, exist_ok=True)
        return path

    def _path(self, username: str, filename: str) -> str:
        directory = self._user_dir(username)
        full = os.path.abspath(os.path.join(directory, safe_name(filename)))
        # Belt and braces: the resolved path must stay inside the user's dir.
        if os.path.commonpath([full, directory]) != directory:
            raise StorageError("Invalid filename")
        return full

    def ensure_user_space(self, username: str) -> None:
        self._user_dir(username)

    def list_files(self, username: str) -> list[dict[str, Any]]:
        directory = self._user_dir(username)
        out: list[dict[str, Any]] = []
        for entry in sorted(os.listdir(directory)):
            full = os.path.join(directory, entry)
            if os.path.isfile(full):
                stat = os.stat(full)
                out.append(
                    {"filename": entry, "size": stat.st_size, "last_modified": stat.st_mtime}
                )
        return out

    def read_file(self, username: str, filename: str) -> bytes:
        path = self._path(username, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(filename)
        with open(path, "rb") as fh:
            return fh.read()

    def write_file(self, username: str, filename: str, content: bytes) -> None:
        path = self._path(username, filename)
        # Write to a temp file then move, so a crash can't leave a half file.
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(content)
        os.replace(tmp, path)

    def delete_file(self, username: str, filename: str) -> None:
        path = self._path(username, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(filename)
        os.remove(path)

    def rename_file(self, username: str, filename: str, new_name: str) -> None:
        old = self._path(username, filename)
        new = self._path(username, new_name)
        if not os.path.exists(old):
            raise FileNotFoundError(filename)
        if os.path.exists(new):
            raise StorageError(f"{new_name} already exists")
        os.rename(old, new)

    def file_exists(self, username: str, filename: str) -> bool:
        return os.path.isfile(self._path(username, filename))

    def materialize_dir(self, username: str) -> str:
        return self._user_dir(username)


class FileCloudStorage(StorageBackend):
    """
    FileCloud-backed storage.

    Files live in the tenant, so they survive Render restarts and show up in
    FileCloud's admin portal (Manage Files) where you can browse each user's
    folder. A local staging copy is made only when code needs to be executed.
    """

    name = "filecloud"

    def __init__(self, client: Optional[FileCloudClient] = None) -> None:
        self.client = client or _filecloud_singleton
        os.makedirs(WORKSPACE_DIR, exist_ok=True)

    @staticmethod
    def _wrap(exc: Exception) -> StorageError:
        return StorageError(str(exc))

    def ensure_user_space(self, username: str) -> None:
        try:
            self.client.ensure_user_folder(safe_user(username))
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def list_files(self, username: str) -> list[dict[str, Any]]:
        try:
            return self.client.list_files(safe_user(username))
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def read_file(self, username: str, filename: str) -> bytes:
        try:
            return self.client.download_file(safe_user(username), safe_name(filename))
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def write_file(self, username: str, filename: str, content: bytes) -> None:
        try:
            self.client.upload_file(safe_user(username), safe_name(filename), content)
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def delete_file(self, username: str, filename: str) -> None:
        try:
            self.client.delete_file(safe_user(username), safe_name(filename))
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def rename_file(self, username: str, filename: str, new_name: str) -> None:
        try:
            self.client.rename_file(
                safe_user(username), safe_name(filename), safe_name(new_name)
            )
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def file_exists(self, username: str, filename: str) -> bool:
        try:
            return self.client.file_exists(safe_user(username), safe_name(filename))
        except FileCloudError as exc:
            raise self._wrap(exc) from exc

    def materialize_dir(self, username: str) -> str:
        """Download every file in the user's folder into a local staging dir."""
        user = safe_user(username)
        staging = os.path.join(WORKSPACE_DIR, user)
        os.makedirs(staging, exist_ok=True)
        for meta in self.list_files(user):
            name = meta["filename"]
            try:
                data = self.read_file(user, name)
            except StorageError as exc:
                log.warning("staging %s/%s failed: %s", user, name, exc)
                continue
            with open(os.path.join(staging, safe_name(name)), "wb") as fh:
                fh.write(data)
        return staging

    def health(self) -> dict[str, Any]:
        try:
            info = self.client.health_check()
            return {
                "backend": self.name,
                "ok": True,
                "tenant": self.client.base_url,
                "service_account": self.client.username,
                "root_folder": f"/{self.client.root}",
                "detail": info.get("message", ""),
            }
        except FileCloudError as exc:
            return {"backend": self.name, "ok": False, "error": str(exc)}


class _StagedWriteThrough(FileCloudStorage):
    """
    FileCloud storage that also keeps the local staging copy current on write.

    Saves a round trip: after a save, the runner can execute immediately
    without re-downloading the file it just uploaded.
    """

    name = "filecloud"

    def write_file(self, username: str, filename: str, content: bytes) -> None:
        super().write_file(username, filename, content)
        user, name = safe_user(username), safe_name(filename)
        staging = os.path.join(WORKSPACE_DIR, user)
        os.makedirs(staging, exist_ok=True)
        with open(os.path.join(staging, name), "wb") as fh:
            fh.write(content)

    def delete_file(self, username: str, filename: str) -> None:
        super().delete_file(username, filename)
        stale = os.path.join(WORKSPACE_DIR, safe_user(username), safe_name(filename))
        if os.path.exists(stale):
            os.remove(stale)

    def rename_file(self, username: str, filename: str, new_name: str) -> None:
        super().rename_file(username, filename, new_name)
        staging = os.path.join(WORKSPACE_DIR, safe_user(username))
        old = os.path.join(staging, safe_name(filename))
        if os.path.exists(old):
            os.replace(old, os.path.join(staging, safe_name(new_name)))


# ── Backend selection ──────────────────────────────────────────────────────────
_storage: Optional[StorageBackend] = None


def _build_storage() -> StorageBackend:
    if STORAGE_BACKEND in ("filecloud", "fc"):
        candidate = _StagedWriteThrough()
        try:
            candidate.client.login()
            log.info("Storage backend: filecloud (%s)", candidate.client.base_url)
            return candidate
        except FileCloudError as exc:
            if not FALLBACK_TO_LOCAL:
                raise
            log.error(
                "FileCloud unavailable (%s) — falling back to local disk. "
                "Files will NOT persist across Render restarts.",
                exc,
            )
            return LocalStorage()

    log.info("Storage backend: local (%s)", UPLOAD_DIR)
    return LocalStorage()


def get_storage() -> StorageBackend:
    """Lazily build the configured backend. Import this from routers."""
    global _storage
    if _storage is None:
        _storage = _build_storage()
    return _storage


def reset_storage() -> None:
    """Drop the cached backend — used by tests and the /health/storage refresh."""
    global _storage
    _storage = None
