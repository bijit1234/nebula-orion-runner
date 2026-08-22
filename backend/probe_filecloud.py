#!/usr/bin/env python
"""
FileCloud API probe — run this FIRST, before deploying.

FileCloud's REST API is not reliably documented and endpoint names differ
between versions, so rather than trusting a guess, this script asks your own
tenant what actually works. It logs in, then tries each candidate endpoint and
prints the raw response, so you can see exactly what FileCloud replies.

USAGE
-----
    cd backend
    # either export the vars or put them in backend/.env
    export FILECLOUD_URL=https://yourtenant.filecloudonline.com
    export FILECLOUD_ADMIN_USER=nebula-service
    export FILECLOUD_ADMIN_PASS='...'
    python probe_filecloud.py

At the end it prints a SUMMARY telling you which endpoints worked and, if any
defaults were wrong, the exact FC_EP_* / FC_PARAM_* env vars to set on Render.

This script only touches a throwaway folder (/<root>/__probe__), and cleans up
after itself.
"""

from __future__ import annotations

import os
import sys
import xml.dom.minidom

import requests
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("FILECLOUD_URL", "").rstrip("/")
USER = os.getenv("FILECLOUD_ADMIN_USER", "")
PASS = os.getenv("FILECLOUD_ADMIN_PASS", "")
ROOT = os.getenv("FILECLOUD_ROOT_FOLDER", "Nebula").strip("/")

PROBE_USER = "__probe__"
PROBE_FILE = "nebula_probe.txt"
PROBE_BODY = b"nebula probe - safe to delete\n"

session = requests.Session()
session.headers.update({"User-Agent": "nebula-probe/1.0"})

results: dict[str, str] = {}
hints: list[str] = []


def show(title: str, resp: requests.Response, limit: int = 900) -> str:
    """Print a response in readable form and return its body."""
    body = (resp.text or "").strip()
    print(f"\n{'─' * 72}\n{title}")
    print(f"  {resp.request.method} {resp.url}")
    print(f"  HTTP {resp.status_code}   Content-Type: {resp.headers.get('Content-Type', '?')}")
    if resp.cookies:
        print(f"  Set-Cookie: {dict(resp.cookies)}")

    pretty = body
    if body.startswith("<"):
        try:
            pretty = xml.dom.minidom.parseString(body).toprettyxml(indent="  ").strip()
        except Exception:
            pass
    print("  Body:")
    for line in pretty[:limit].splitlines():
        print(f"    {line}")
    if len(pretty) > limit:
        print(f"    ... [{len(pretty) - limit} more chars]")
    return body


def looks_ok(body: str) -> bool:
    """FileCloud success looks like <result>1</result> or "result":"1"."""
    low = body.lower().replace(" ", "")
    return "<result>1</result>" in low or '"result":1' in low or '"result":"1"' in low


def record(label: str, body: str) -> bool:
    ok = looks_ok(body)
    results[label] = "WORKED" if ok else "FAILED"
    print(f"  ==> {'✅ WORKED' if ok else '❌ did not report result=1'}")
    return ok


# ── 0. sanity ─────────────────────────────────────────────────────────────────
if not (URL and USER and PASS):
    sys.exit(
        "Set FILECLOUD_URL, FILECLOUD_ADMIN_USER and FILECLOUD_ADMIN_PASS first "
        "(env vars or backend/.env)."
    )

print("=" * 72)
print("FileCloud API probe")
print(f"  tenant : {URL}")
print(f"  account: {USER}")
print(f"  root   : /{ROOT}")
print("=" * 72)


# ── 1. login ──────────────────────────────────────────────────────────────────
# Two variants: bare credentials, and credentials + device identification.
login_ok = False
for label, payload in [
    ("loginguest (bare)", {"userid": USER, "password": PASS}),
    (
        "loginguest (+device)",
        {
            "userid": USER,
            "password": PASS,
            "appname": "explorer",
            "deviceid": "nebula-probe",
            "devicetype": "Web",
        },
    ),
]:
    resp = session.post(f"{URL}/core/loginguest", data=payload, timeout=30)
    body = show(f"1. LOGIN — {label}", resp)
    if record(f"login: {label}", body):
        login_ok = True
        if "device" in label:
            hints.append(
                "Login needed device params — keep FC_APPNAME/FC_DEVICEID/FC_DEVICETYPE set."
            )
        break

if not login_ok:
    print("\n" + "!" * 72)
    print("LOGIN FAILED — everything below will fail too. Common causes:")
    print("  * wrong tenant URL (must include https:// and the full host)")
    print("  * the account has 2FA enabled — turn it off for this service account")
    print("  * the account is an ADMIN-only login; create a normal *user* account")
    print("  * the tenant restricts API/web access by IP or policy")
    print("!" * 72)
    sys.exit(1)

# Does the API honour a JSON request, or is it XML only?
resp = session.get(f"{URL}/core/getaccountinfo", params={"responseformat": "json"}, timeout=30)
body = show("1b. getaccountinfo (asked for JSON)", resp)
is_json = body.startswith("{") or "json" in resp.headers.get("Content-Type", "").lower()
print(f"  ==> API returns {'JSON' if is_json else 'XML'} — the client parses both.")


# ── 2. create folders ─────────────────────────────────────────────────────────
resp = session.post(f"{URL}/core/createfolder", data={"path": "/", "name": ROOT}, timeout=30)
record("createfolder (root)", show(f"2. CREATE FOLDER /{ROOT}", resp))

resp = session.post(
    f"{URL}/core/createfolder", data={"path": f"/{ROOT}", "name": PROBE_USER}, timeout=30
)
record("createfolder (user)", show(f"2b. CREATE FOLDER /{ROOT}/{PROBE_USER}", resp))

# If '/' as the parent failed, the user root may be namespaced by username.
if results.get("createfolder (root)") == "FAILED":
    resp = session.post(
        f"{URL}/core/createfolder", data={"path": f"/{USER}", "name": ROOT}, timeout=30
    )
    if record("createfolder (root under /<user>)", show(f"2c. CREATE FOLDER /{USER}/{ROOT}", resp)):
        hints.append(
            f"Your user root is /{USER}, not / — set FILECLOUD_ROOT_FOLDER={USER}/{ROOT}"
        )

REMOTE_DIR = f"/{ROOT}/{PROBE_USER}"


# ── 3. upload ─────────────────────────────────────────────────────────────────
# Variant A: multipart form (what most REST APIs expect).
resp = session.post(
    f"{URL}/core/upload",
    params={"appname": "explorer", "path": REMOTE_DIR, "filename": PROBE_FILE},
    data={"path": REMOTE_DIR, "appname": "explorer"},
    files={"file": (PROBE_FILE, PROBE_BODY, "application/octet-stream")},
    timeout=60,
)
multipart_ok = record("upload (multipart)", show("3. UPLOAD — multipart", resp))

# Variant B: raw body with offset/complete (FileCloud's chunked-upload style).
if not multipart_ok:
    resp = session.post(
        f"{URL}/core/upload",
        params={
            "appname": "explorer",
            "path": REMOTE_DIR,
            "filename": PROBE_FILE,
            "offset": 0,
            "complete": 1,
        },
        data=PROBE_BODY,
        timeout=60,
    )
    if record("upload (raw body)", show("3b. UPLOAD — raw body", resp)):
        hints.append("Multipart upload failed but raw worked — set FC_UPLOAD_MODE=raw")


# ── 4. list ───────────────────────────────────────────────────────────────────
for label, endpoint, params in [
    ("getfilelist", "/core/getfilelist", {"path": REMOTE_DIR, "start": 0, "end": 100}),
    ("getfolderlist", "/core/getfolderlist", {"path": REMOTE_DIR}),
]:
    resp = session.get(f"{URL}{endpoint}", params=params, timeout=30)
    body = show(f"4. LIST — {label}", resp)
    found = PROBE_FILE in body
    results[f"list: {label}"] = "WORKED" if found else "FAILED"
    print(f"  ==> {'✅ probe file listed' if found else '❌ probe file not in listing'}")
    if found and label != "getfilelist":
        hints.append(f"Listing works via {endpoint} — set FC_EP_FILE_LIST={endpoint}")
        break
    if found:
        break


# ── 5. download ───────────────────────────────────────────────────────────────
remote_file = f"{REMOTE_DIR}/{PROBE_FILE}"
for label, endpoint, params in [
    ("downloadfile (filepath)", "/core/downloadfile", {"filepath": remote_file}),
    ("downloadfile (path+filename)", "/core/downloadfile",
     {"path": REMOTE_DIR, "filename": PROBE_FILE}),
    ("download (path)", "/core/download", {"path": remote_file}),
]:
    resp = session.get(f"{URL}{endpoint}", params=params, timeout=30)
    body = show(f"5. DOWNLOAD — {label}", resp, limit=300)
    got = PROBE_BODY.decode().strip() in body
    results[f"download: {label}"] = "WORKED" if got else "FAILED"
    print(f"  ==> {'✅ content matched' if got else '❌ content not returned'}")
    if got:
        if "download (path)" == label:
            hints.append("Set FC_EP_DOWNLOAD=/core/download")
        break


# ── 6. rename ─────────────────────────────────────────────────────────────────
for label, endpoint, payload in [
    ("renamefile", "/core/renamefile",
     {"path": REMOTE_DIR, "name": PROBE_FILE, "newname": "nebula_probe2.txt"}),
    ("rename", "/core/rename",
     {"path": REMOTE_DIR, "name": PROBE_FILE, "newname": "nebula_probe2.txt"}),
]:
    resp = session.post(f"{URL}{endpoint}", data=payload, timeout=30)
    if record(f"rename: {label}", show(f"6. RENAME — {label}", resp)):
        if label == "rename":
            hints.append("Set FC_EP_RENAME=/core/rename")
        PROBE_FILE = "nebula_probe2.txt"
        break


# ── 7. delete (also the cleanup) ──────────────────────────────────────────────
for label, endpoint, payload in [
    ("deletefile (path+name)", "/core/deletefile", {"path": REMOTE_DIR, "name": PROBE_FILE}),
    ("deletefile (full path)", "/core/deletefile", {"path": f"{REMOTE_DIR}/{PROBE_FILE}"}),
]:
    resp = session.post(f"{URL}{endpoint}", data=payload, timeout=30)
    if record(f"delete: {label}", show(f"7. DELETE — {label}", resp)):
        if "full path" in label:
            hints.append(
                "Delete needs the full path in `path` — adjust delete_file() in filecloud.py"
            )
        break

# Remove the probe folder so your tenant is left clean.
session.post(
    f"{URL}/core/deletefolder", data={"path": f"/{ROOT}", "name": PROBE_USER}, timeout=30
)


# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("SUMMARY")
print("=" * 72)
width = max(len(k) for k in results) if results else 10
for label, status in results.items():
    icon = "✅" if status == "WORKED" else "❌"
    print(f"  {icon} {label.ljust(width)}  {status}")

print(f"\n  Response format: {'JSON' if is_json else 'XML'}")
print(f"  Session cookies: {list(session.cookies.keys())}")

if hints:
    print("\n  ACTION REQUIRED — set these on Render (Environment tab):")
    for hint in hints:
        print(f"    * {hint}")
else:
    print("\n  No overrides needed — the defaults in filecloud.py match your tenant. 🎉")

failed = [k for k, v in results.items() if v == "FAILED"]
if failed:
    print(
        "\n  Some probes failed. That is expected — this script tries several\n"
        "  variants of each call and stops at the first that works. Only worry\n"
        "  if an ENTIRE category (upload / list / download / delete) failed."
    )
print()
