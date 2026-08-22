# Deploying Nebula with FileCloud storage

A runbook for wiring your already-deployed Render app to a FileCloud Online
trial, and for surviving the day the trial ends.

---

## 0. The thing to understand first

FileCloud is an **enterprise file sync & share platform** (like a self-hostable
Dropbox/Box), not an application host. There is no way to deploy a React build
or a FastAPI server *onto* FileCloud. It has no runtime, no `git push` target,
no container support.

So the plan is not "deploy to FileCloud". It is:

```
   Browser
      │
      ▼
   React frontend            ← Render Static Site
      │  (axios, JWT)
      ▼
   FastAPI backend           ← Render Web Service  (your existing deploy)
      │
      ├── Postgres ─────────── users, execution history
      │
      └── StorageBackend ───── FileCloud tenant
                                 /Nebula/alice/main.py
                                 /Nebula/bob/hello.py
```

Your app keeps owning **login and accounts** (JWT + the `users` table).
FileCloud owns **the files**. You get the thing you actually wanted: an admin
portal where you can browse each user's folder and see what they created.

One consequence of the design you picked (single service account + per-user
folders) worth knowing up front: FileCloud's **Users** page will only ever list
your one service account. Per-user visibility comes from the *folder tree*, not
the user list. If you later want each Nebula user to appear as a real FileCloud
user with their own quota, that needs the admin API — see §6.

---

## 1. What changed in your code

I restructured the storage path so FileCloud is swappable rather than welded in.

**New files**

| File | Purpose |
| --- | --- |
| `backend/app/services/storage.py` | `StorageBackend` interface, `LocalStorage`, `FileCloudStorage`, backend selection |
| `backend/probe_filecloud.py` | Discovers your tenant's real API before you deploy |

**Rewritten**

`backend/app/services/filecloud.py` — the previous version could not work. It
sent `Accept: application/json` then called `resp.json()` on every reply; if
FileCloud answers XML that raises on every call. Worse, each method caught the
exception and then `return True` anyway, so uploads and deletes reported
success while doing nothing. The rewrite parses XML *or* JSON, checks the
`<result>` field, and raises `FileCloudError` on failure.

`backend/app/routers/files.py` — every handler now goes through the storage
layer and is **namespaced by `current_user.username`**. Previously all users
shared one `./uploads` directory, so any logged-in user saw and could delete
everyone else's files, and two users could not both have a `main.py`. The HTTP
surface is unchanged, so the frontend needs no edits.

`backend/app/routers/execution.py` — fetches the file from storage into a local
staging directory before running it (a subprocess can only execute something
real), and tracks runs per user.

`backend/app/runner.py` — run state is keyed `username/filename` instead of
`filename`, so two users running `main.py` no longer collide. Also added a hard
`MAX_EXECUTION_SECONDS` kill, because one `while True:` would otherwise pin
your Render instance's CPU indefinitely.

`backend/app/auth.py` — registration now validates the username charset (it
becomes a folder name, and `../alice` must not collide with `alice`) and
pre-creates the user's FileCloud folder so it appears at signup rather than
first upload.

`backend/requirements.txt` — added `requests` (the FileCloud client imports it
and it was missing, which would have crashed your Render build the moment
anything touched FileCloud) and `psycopg2-binary` (for §4).

**One migration note:** files previously sat flat in `./uploads/main.py`; they
now live in `./uploads/<username>/main.py`. Any existing local files won't be
visible until you move them into a username subfolder. On Render this is moot —
the ephemeral disk has already discarded them.

---

## 2. Set up the FileCloud trial

Sign up at filecloud.com for a **FileCloud Online** trial. You'll get a tenant
URL like `https://yourname.filecloudonline.com` plus admin credentials.

Then, in the FileCloud **admin portal**:

1. **Create a normal user account for the app.** Something like
   `nebula-service` with a long random password. Do not use your admin login:
   in FileCloud the admin account and the file-owning user account are
   different things, and admin credentials often cannot call the user file API
   at all. This account will own every Nebula user's files.

2. **Disable 2FA / MFA for that account.** A server cannot type a one-time
   code. If your tenant enforces 2FA globally, look for a per-user or
   per-policy exemption.

3. **Check for anything blocking programmatic access.** Depending on version
   there may be policy settings around API access, device management, or device
   approval that reject non-browser logins by default. If your tenant has a
   device-approval workflow, the first login from Render will show up as a
   pending device that you approve once.

4. **Note the exact tenant URL**, including `https://` and no trailing slash.

I could not verify the current admin-portal menu labels (my sandbox has no
network access to filecloud.com), so treat the names above as descriptions
rather than exact paths — they've moved between versions. The probe in the next
step will tell you definitively whether the account works, which matters more
than finding the right menu.

---

## 3. Run the probe before you deploy

This is the step that saves you a day of guessing. FileCloud's REST API isn't
publicly documented in a stable form and endpoint names differ between
versions, so `probe_filecloud.py` asks *your* tenant what actually works.

```bash
cd backend
# activate your venv first
export FILECLOUD_URL=https://yourtenant.filecloudonline.com
export FILECLOUD_ADMIN_USER=nebula-service
export FILECLOUD_ADMIN_PASS='your-password'
python probe_filecloud.py
```

It logs in, then tries each candidate endpoint for create-folder, upload, list,
download, rename and delete, printing the raw response for each. It works in a
throwaway `/Nebula/__probe__` folder and cleans up after itself.

Read the **SUMMARY** at the bottom. Either it says the defaults match your
tenant, or it prints the exact `FC_EP_*` / `FC_PARAM_*` env vars to set. Those
override the endpoint names at runtime, so you can correct the integration from
Render's dashboard without touching code.

If login itself fails, nothing else matters — go back to §2. The most common
causes are a wrong tenant URL, 2FA still on, or using the admin login instead
of a normal user account.

---

## 4. Configure your existing Render service

Two things about Render will silently eat your data, and you should fix them in
the same pass.

**The free tier's filesystem is ephemeral.** Anything written to disk vanishes
on every deploy, restart and idle spin-down. That's exactly why external
storage is the right call here — but it also means your **SQLite database is
being wiped too**. Every registered user disappears on each restart, which will
look like FileCloud losing data when it isn't. Create a Render Postgres
instance and point `DATABASE_URL` at its **internal** connection string.
(Render's free database tier has an expiry window — check the current terms so
its eventual deletion doesn't surprise you.)

**Free web services spin down when idle**, so the first request after a quiet
spell takes roughly a minute. Don't mistake that for a FileCloud timeout.

In your service's **Environment** tab:

| Variable | Value |
| --- | --- |
| `STORAGE_BACKEND` | `filecloud` |
| `FILECLOUD_URL` | `https://yourtenant.filecloudonline.com` |
| `FILECLOUD_ADMIN_USER` | `nebula-service` |
| `FILECLOUD_ADMIN_PASS` | the password (mark as secret) |
| `FILECLOUD_ROOT_FOLDER` | `Nebula` |
| `STORAGE_FALLBACK_LOCAL` | `true` while testing, `false` once it works |
| `DATABASE_URL` | your Render Postgres internal URL |
| `SECRET_KEY` | 32+ random bytes — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_ORIGINS` | your frontend URL, e.g. `https://nebula-frontend.onrender.com` |
| `ADMIN_PASSWORD` | change it from `password123` |
| `MAX_EXECUTION_SECONDS` | `30` |

Plus any `FC_EP_*` overrides the probe asked for.

`requirements.txt` changed, so trigger a **manual deploy with cache cleared**
rather than relying on an incremental build.

Then verify:

```bash
curl https://your-backend.onrender.com/health/storage
```

You want `"backend": "filecloud"` and `"ok": true`. If it says
`"backend": "local"`, the FileCloud login failed and the app fell back to
ephemeral disk — the `error` field tells you why. This is the single most
useful thing to check after any config change.

A note on `STORAGE_FALLBACK_LOCAL`: `true` keeps the app usable if FileCloud is
unreachable, which is friendly during setup but means a broken config looks
like a working app that quietly loses files. Once `/health/storage` is green,
set it to `false` so misconfiguration fails loudly.

**Frontend:** Create React App bakes `REACT_APP_API_URL` in at *build* time, so
if you change your backend URL you must rebuild the static site, not just
restart it. Confirm your static site sets `REACT_APP_API_URL` to the backend
URL and has a rewrite rule sending `/*` to `/index.html` for client-side
routing.

---

## 5. Seeing your users and their files

This was the goal, so here's where each piece lives.

**Accounts** live in your Postgres `users` table. Your API already exposes the
current user; there's no admin list endpoint yet, so for now query the database
from Render's dashboard or psql:
`SELECT username, created_at FROM users ORDER BY created_at DESC;`

**Files** live in FileCloud. In the admin portal open the file browser for the
`nebula-service` account and navigate to `/Nebula/`. You'll see one folder per
user, each holding their `.py` files, with FileCloud's own versioning, sharing,
audit log and download counters on top. That audit trail is the genuinely nice
part — it shows you every upload and download with timestamps, which your app
doesn't record.

**Execution history** is in Postgres, in `execution_history`, joined to the user
by `user_id`.

---

## 6. The 15-day exit plan

Take this seriously — the trial dies on a fixed date and, if you've pointed
`STORAGE_BACKEND` at it, your file features die with it. The storage
abstraction means the switch is one environment variable, but you need the data
out first.

**A few days before expiry**, while the API still works, pull everything down:

```bash
cd backend
python - <<'EOF'
import os
os.environ["STORAGE_BACKEND"] = "filecloud"
from app.services.storage import get_storage
s = get_storage()
for user in ["alice", "bob"]:              # your real usernames
    print(user, "->", s.materialize_dir(user))
EOF
```

`materialize_dir` downloads that user's whole folder into `./workspace/<user>/`,
so this doubles as your backup. Copy `./workspace/` somewhere safe.

**Also, if this is for a demo or report:** screenshot the FileCloud admin portal
showing the user folders, a file's version history, and the audit log *before*
the trial ends. Once it expires you cannot get those screenshots back, and
they're the best evidence that the integration worked.

**Then pick where files live next.** Set `STORAGE_BACKEND=local` and the app
keeps working immediately — but remember local disk is ephemeral on Render's
free tier, so that's a stopgap, not a destination. For something permanent,
the sensible options are object storage with a real free tier: Cloudflare R2
(~10 GB free, S3-compatible, no egress fees), Backblaze B2, or Supabase Storage
if you'd like a dashboard closer to what FileCloud gave you. Any of them is a
new `StorageBackend` subclass — implement the seven methods in `storage.py`,
add it to `_build_storage()`, and nothing else in the app changes. That's
roughly 80 lines with `boto3` for an S3-compatible target.

If you want to keep FileCloud specifically, ask their sales team about
education or startup pricing before the trial lapses; they have also offered
limited free tiers in the past, so it's worth asking what's currently
available rather than assuming.

---

## 7. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `/health/storage` shows `backend: local` | FileCloud login failed; read the `error` field |
| `login rejected` | Wrong URL, 2FA enabled, or using the admin account instead of a user account |
| Everything works except upload | Multipart form rejected — set `FC_UPLOAD_MODE=raw` |
| File list always empty | Wrong list endpoint or path root; rerun the probe |
| `createfolder` fails on `/` | Your user root is namespaced; the probe suggests a `FILECLOUD_ROOT_FOLDER` value |
| Users vanish after redeploy | Still on SQLite — move to Postgres (§4) |
| Files vanish after redeploy | Still on `local` backend with Render's ephemeral disk |
| First request takes ~1 minute | Render free tier cold start, not FileCloud |
| CORS errors in the browser | `ALLOWED_ORIGINS` doesn't exactly match the frontend origin |
| 502 from file endpoints | FileCloud unreachable and `STORAGE_FALLBACK_LOCAL=false` — correct behaviour, fix the config |
| `ModuleNotFoundError: requests` | Deployed without clearing the build cache after `requirements.txt` changed |

---

## 9. Shipping this to Render via GitHub

Render auto-deploys from `github.com/bijit1234/nebula-orion-runner`, so nothing
above reaches production until you push.

There *was* a line-endings problem: your working tree is CRLF (Windows), the
repo stores LF, and `core.autocrlf` is unset, so `git status` listed ~26 files
as modified that nobody edited. Adding `.gitattributes` fixed it — git now
reports only the 8 files that genuinely changed, so no separate normalising
commit is needed. Just commit:

```bash
cd E:\my-cloud2\nebula-orion-runner
git add .gitattributes .gitignore backend/ FILECLOUD_DEPLOYMENT.md
git commit -m "feat: swappable storage backend with FileCloud support

- add StorageBackend abstraction (local + FileCloud) so trial expiry is a
  one-env-var switch
- rewrite FileCloud client: parse XML/JSON, check result, stop reporting
  success on failure
- namespace files and executions per user (all users previously shared
  ./uploads)
- add probe_filecloud.py to discover the tenant's real API
- add /health/storage, execution timeout, requests + psycopg2 deps"
git push origin main
```

Only these files carry real changes: `.gitignore`, `backend/.env.example`,
`backend/app/auth.py`, `backend/app/main.py`, `backend/app/routers/execution.py`,
`backend/app/routers/files.py`, `backend/app/runner.py`,
`backend/requirements.txt`, plus the new `backend/app/services/`,
`backend/probe_filecloud.py`, `.gitattributes` and this document.

Because `requirements.txt` changed, use **Manual Deploy → Clear build cache &
deploy** rather than letting the push trigger an incremental build. Then check
`/health/storage` as in §4.

Pushing before FileCloud is configured is safe: `STORAGE_BACKEND` defaults to
`local`, so the deploy behaves like your current app (with files now separated
per user) until you explicitly flip the variable.

Two things to confirm are *not* in the public repo: `backend/.env` and
`backend/nebula.db`. Your `.gitignore` already covers both and `git ls-files`
confirms neither is tracked — good. Keep it that way; put every secret in
Render's Environment tab, never in the repo.

---

## 10. Security notes

Two things stand out beyond the config above.

You are **running arbitrary user-submitted Python** in the same container as
your web server, as the same user, with network access and your environment
variables — including `FILECLOUD_ADMIN_PASS` — readable via `os.environ`. Any
registered user can read your FileCloud credentials with a three-line script.
The `MAX_EXECUTION_SECONDS` limit I added stops runaway CPU, but it is not a
sandbox. For anything beyond a private demo you'd want execution moved to a
disposable container with no env inheritance, no network, a read-only
filesystem and a memory cap. If this stays a college/portfolio project, at
minimum keep registration closed or the app unadvertised.

Password hashing uses PBKDF2-HMAC-SHA256 at 100k iterations, which is
acceptable. But `passlib[bcrypt]` is already in `requirements.txt` and unused —
either use it or drop the dependency.
