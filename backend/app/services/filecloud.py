"""
FileCloud API client.

Talks to a FileCloud Online tenant (https://<tenant>.filecloudonline.com) using a
single service account. Every Nebula user gets their own folder underneath
FILECLOUD_ROOT_FOLDER, e.g. /Nebula/alice/main.py

WHY THIS FILE IS SHAPED LIKE THIS
---------------------------------
FileCloud's REST API is not publicly documented in a stable, machine-readable
form, and the endpoint names / parameter names have historically differed
between versions. So instead of hard-coding assumptions:

  * every endpoint path and parameter name is overridable via env vars
    (FC_EP_* and FC_PARAM_*), so you can correct them WITHOUT editing code;
  * responses are parsed as XML *or* JSON, whichever the server sends;
  * every call actually inspects the <result> field and raises FileCloudError
    on failure, instead of returning True unconditionally.

Run `python probe_filecloud.py` against your tenant to discover the real
endpoint names, then set any FC_EP_* / FC_PARAM_* overrides it reports.
"""

from __future__ import annotations

import os
import logging
import xml.etree.ElementTree as ET
from typing import Any, Optional

import requests

log = logging.getLogger("nebula.filecloud")

# ── Connection settings ────────────────────────────────────────────────────────
FILECLOUD_URL = os.getenv("FILECLOUD_URL", "").rstrip("/")
FILECLOUD_USER = os.getenv("FILECLOUD_ADMIN_USER", "")
FILECLOUD_PASS = os.getenv("FILECLOUD_ADMIN_PASS", "")
FILECLOUD_ROOT = os.getenv("FILECLOUD_ROOT_FOLDER", "Nebula").strip("/")

# Some FileCloud deployments reject logins that don't identify the client.
FC_APPNAME = os.getenv("FC_APPNAME", "explorer")
FC_DEVICEID = os.getenv("FC_DEVICEID", "nebula-backend")
FC_DEVICETYPE = os.getenv("FC_DEVICETYPE", "Web")

TIMEOUT = int(os.getenv("FILECLOUD_TIMEOUT", "30"))

# ── Endpoints (override via env if the probe says otherwise) ───────────────────
EP_LOGIN = os.getenv("FC_EP_LOGIN", "/core/loginguest")
EP_WHOAMI = os.getenv("FC_EP_WHOAMI", "/core/getaccountinfo")
EP_CREATE_FOLDER = os.getenv("FC_EP_CREATE_FOLDER", "/core/createfolder")
EP_FILE_LIST = os.getenv("FC_EP_FILE_LIST", "/core/getfilelist")
EP_UPLOAD = os.getenv("FC_EP_UPLOAD", "/core/upload")
EP_DOWNLOAD = os.getenv("FC_EP_DOWNLOAD", "/core/downloadfile")
EP_DELETE = os.getenv("FC_EP_DELETE", "/core/deletefile")
EP_RENAME = os.getenv("FC_EP_RENAME", "/core/renamefile")

# ── Parameter names (override via env if the probe says otherwise) ─────────────
P_USER = os.getenv("FC_PARAM_USER", "userid")
P_PASS = os.getenv("FC_PARAM_PASS", "password")
P_PATH = os.getenv("FC_PARAM_PATH", "path")
P_NAME = os.getenv("FC_PARAM_NAME", "name")
P_NEWNAME = os.getenv("FC_PARAM_NEWNAME", "newname")
P_FILEPATH = os.getenv("FC_PARAM_FILEPATH", "filepath")

# "multipart" sends a normal file upload; "raw" streams the bytes as the body.
UPLOAD_MODE = os.getenv("FC_UPLOAD_MODE", "multipart").lower()

# Ask for JSON where supported; harmless when the server insists on XML.
JSON_HINT = {"responseformat": "json"}


class FileCloudError(RuntimeError):
    """Raised when FileCloud reports a failure or is unreachable."""


def _truthy_result(payload: dict[str, Any]) -> bool:
    """
    FileCloud signals success with result == 1 (sometimes "1", sometimes "ok").
    Treat a missing result as failure so problems surface loudly.
    """
    raw = payload.get("result", payload.get("Result"))
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "ok", "success")


def _xml_to_dict(root: ET.Element) -> dict[str, Any]:
    """
    Flatten a FileCloud XML reply into a dict.

    Typical shapes:
      <command><type>createfolder</type><result>1</result><message/></command>
      <?xml..?><entry><name>a.py</name>..</entry><entry>..</entry>
    Repeated <entry> children are collected into payload["entry"].
    """
    out: dict[str, Any] = {}
    entries: list[dict[str, str]] = []

    def absorb(node: ET.Element) -> None:
        for child in node:
            if child.tag.lower() == "entry":
                entries.append(
                    {gc.tag: (gc.text or "") for gc in child} or {"name": child.text or ""}
                )
            elif len(child):
                absorb(child)
            else:
                out.setdefault(child.tag, (child.text or "").strip())

    if root.tag.lower() == "entry":
        entries.append({gc.tag: (gc.text or "") for gc in root})
    else:
        absorb(root)

    if entries:
        out["entry"] = entries
    return out


def _parse(resp: requests.Response) -> dict[str, Any]:
    """Parse a FileCloud response as JSON or XML, whichever it actually is."""
    body = (resp.text or "").strip()
    if not body:
        return {}

    ctype = resp.headers.get("Content-Type", "").lower()
    if "json" in ctype or body[:1] in ("{", "["):
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {"entry": data}
        except ValueError:
            pass

    try:
        # Strip any XML prolog, then wrap in a synthetic root element.
        # FileCloud commonly returns several sibling <entry> blocks with no
        # single enclosing root, which is not well-formed XML on its own.
        xml_body = body
        if xml_body.startswith("<?"):
            end = xml_body.find("?>")
            if end != -1:
                xml_body = xml_body[end + 2:].strip()
        return _xml_to_dict(ET.fromstring(f"<root>{xml_body}</root>"))
    except ET.ParseError:
        return {"_raw": body[:2000]}


class FileCloudClient:
    """Thin, fail-loud wrapper around the FileCloud user API."""

    def __init__(self) -> None:
        self.base_url = FILECLOUD_URL
        self.username = FILECLOUD_USER
        self.password = FILECLOUD_PASS
        self.root = FILECLOUD_ROOT
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "nebula-orion-runner/1.0"})
        self._authenticated = False
        self._root_ready = False

    # ── plumbing ──────────────────────────────────────────────────────────────
    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}{endpoint}"

    def _call(
        self,
        endpoint: str,
        *,
        method: str = "POST",
        data: Optional[dict] = None,
        params: Optional[dict] = None,
        files: Optional[dict] = None,
        content: Optional[bytes] = None,
        raw: bool = False,
        _retry: bool = True,
    ) -> Any:
        """
        Make one API call, re-authenticating once if the session has expired.
        Returns the parsed dict, or the raw Response when raw=True.
        """
        query = {**JSON_HINT, **(params or {})}
        try:
            resp = self.session.request(
                method,
                self._url(endpoint),
                data=content if content is not None else data,
                params=query,
                files=files,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise FileCloudError(f"{endpoint} unreachable: {exc}") from exc

        # An expired session usually shows up as a 401/403 or a login redirect.
        looks_logged_out = resp.status_code in (401, 403) or (
            "loginguest" in resp.text[:400] or "not logged in" in resp.text[:400].lower()
        )
        if looks_logged_out and _retry and endpoint != EP_LOGIN:
            log.info("FileCloud session expired — re-authenticating")
            self._authenticated = False
            self.login()
            return self._call(
                endpoint,
                method=method,
                data=data,
                params=params,
                files=files,
                content=content,
                raw=raw,
                _retry=False,
            )

        if raw:
            return resp

        payload = _parse(resp)
        if resp.status_code >= 400:
            raise FileCloudError(
                f"{endpoint} returned HTTP {resp.status_code}: "
                f"{payload.get('message') or payload.get('_raw', '')}"
            )
        return payload

    def _expect_ok(self, endpoint: str, payload: dict[str, Any]) -> None:
        if not _truthy_result(payload):
            raise FileCloudError(
                f"{endpoint} failed: {payload.get('message') or payload or 'no result field'}"
            )

    # ── authentication ────────────────────────────────────────────────────────
    def login(self) -> bool:
        if not self.configured:
            raise FileCloudError(
                "FileCloud is not configured — set FILECLOUD_URL, "
                "FILECLOUD_ADMIN_USER and FILECLOUD_ADMIN_PASS"
            )

        payload = self._call(
            EP_LOGIN,
            data={
                P_USER: self.username,
                P_PASS: self.password,
                "appname": FC_APPNAME,
                "deviceid": FC_DEVICEID,
                "devicetype": FC_DEVICETYPE,
            },
            _retry=False,
        )
        if not _truthy_result(payload):
            raise FileCloudError(f"login rejected: {payload.get('message') or payload}")

        self._authenticated = True
        log.info("FileCloud login OK as %s", self.username)
        return True

    def ensure_auth(self) -> None:
        if not self._authenticated:
            self.login()

    def health_check(self) -> dict[str, Any]:
        """Verify credentials and connectivity. Used by /health/storage."""
        self.ensure_auth()
        return self._call(EP_WHOAMI, method="GET")

    # ── paths ─────────────────────────────────────────────────────────────────
    def user_dir(self, username: str) -> str:
        return f"/{self.root}/{username}"

    def file_path(self, username: str, filename: str) -> str:
        return f"{self.user_dir(username)}/{filename}"

    # ── folders ───────────────────────────────────────────────────────────────
    def _create_folder(self, parent: str, name: str) -> None:
        payload = self._call(EP_CREATE_FOLDER, data={P_PATH: parent, P_NAME: name})
        # "already exists" is a success for our purposes.
        if not _truthy_result(payload):
            msg = str(payload.get("message", "")).lower()
            if "exist" not in msg:
                raise FileCloudError(f"createfolder {parent}/{name} failed: {payload}")

    def ensure_user_folder(self, username: str) -> None:
        """Create /<root>/ and /<root>/<username>/ if they aren't there yet."""
        self.ensure_auth()
        if not self._root_ready:
            self._create_folder("/", self.root)
            self._root_ready = True
        self._create_folder(f"/{self.root}", username)

    # ── files ─────────────────────────────────────────────────────────────────
    def list_files(self, username: str) -> list[dict[str, Any]]:
        """Return [{filename, size, last_modified}] for the user's folder."""
        self.ensure_auth()
        payload = self._call(
            EP_FILE_LIST,
            method="GET",
            params={P_PATH: self.user_dir(username), "start": 0, "end": 1000},
        )

        entries = payload.get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]

        files: list[dict[str, Any]] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            # FileCloud marks directories via type="dir"/"folder" or isroot/isdir.
            kind = str(e.get("type", e.get("isdir", ""))).lower()
            if kind in ("dir", "folder", "1", "true"):
                continue
            name = e.get("name") or e.get("filename")
            if not name:
                continue
            try:
                size = int(e.get("size", 0) or 0)
            except (TypeError, ValueError):
                size = 0
            files.append(
                {
                    "filename": name,
                    "size": size,
                    "last_modified": e.get("modified") or e.get("modifiedepoch") or "",
                }
            )
        return files

    def file_exists(self, username: str, filename: str) -> bool:
        return any(f["filename"] == filename for f in self.list_files(username))

    def upload_file(self, username: str, filename: str, content: bytes) -> None:
        """Create or overwrite a file in the user's folder."""
        self.ensure_user_folder(username)
        remote_dir = self.user_dir(username)

        if UPLOAD_MODE == "raw":
            payload = self._call(
                EP_UPLOAD,
                params={
                    "appname": FC_APPNAME,
                    P_PATH: remote_dir,
                    "filename": filename,
                    "offset": 0,
                    "complete": 1,
                },
                content=content,
            )
        else:
            payload = self._call(
                EP_UPLOAD,
                params={"appname": FC_APPNAME, P_PATH: remote_dir, "filename": filename},
                data={P_PATH: remote_dir, "appname": FC_APPNAME},
                files={"file": (filename, content, "application/octet-stream")},
            )

        # Upload sometimes replies with an empty body, or with the new file's
        # entry rather than a result field — both are fine. But an explicit
        # non-truthy result must raise, even with no message attached,
        # otherwise a failed upload would look like a successful one.
        if payload and "result" in payload and not _truthy_result(payload):
            raise FileCloudError(
                f"upload {filename} failed: {payload.get('message') or payload}"
            )

    def download_file(self, username: str, filename: str) -> bytes:
        self.ensure_auth()
        resp = self._call(
            EP_DOWNLOAD,
            method="GET",
            params={
                P_FILEPATH: self.file_path(username, filename),
                P_PATH: self.user_dir(username),
                "filename": filename,
            },
            raw=True,
        )
        if resp.status_code != 200:
            raise FileCloudError(f"download {filename}: HTTP {resp.status_code}")

        # A failed download returns an XML/JSON error with a 200 status.
        ctype = resp.headers.get("Content-Type", "").lower()
        if "xml" in ctype or "json" in ctype:
            payload = _parse(resp)
            if payload and not _truthy_result(payload):
                raise FileCloudError(
                    f"download {filename} failed: {payload.get('message') or payload}"
                )
        return resp.content

    def delete_file(self, username: str, filename: str) -> None:
        self.ensure_auth()
        payload = self._call(
            EP_DELETE,
            data={P_PATH: self.user_dir(username), P_NAME: filename},
        )
        self._expect_ok(EP_DELETE, payload)

    def rename_file(self, username: str, old_name: str, new_name: str) -> None:
        self.ensure_auth()
        payload = self._call(
            EP_RENAME,
            data={
                P_PATH: self.user_dir(username),
                P_NAME: old_name,
                P_NEWNAME: new_name,
            },
        )
        self._expect_ok(EP_RENAME, payload)


# Singleton used by the storage layer.
filecloud = FileCloudClient()
