import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from drmagent.config import settings
from drmagent.gmail.auth import create_authorization_url, exchange_code
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord
from drmagent.orchestrator import load_donors_from_csv, process_donor
from drmagent.security import decrypt_credentials, encrypt_credentials

app = FastAPI(title="DRM Agent", version="1.0.0")

# Demo-only in-memory state. Replace with a database/secure session store in
# production. Two things were hardened even within that constraint:
#   - gmail_credentials are Fernet-encrypted before being stored here (see
#     drmagent/security.py), so a memory dump / logging accident / future
#     bug that serializes `sessions` doesn't hand over a live Gmail token.
#   - entries are swept for staleness (see `_sweep_expired`) so a session
#     dict that's never explicitly logged out of doesn't grow forever and
#     doesn't stay "valid" indefinitely.
sessions: dict[str, dict[str, Any]] = {}
oauth_states: dict[str, dict[str, str]] = {}
donor_records: list[DonorRecord] = []

_session_created_at: dict[str, float] = {}
_oauth_state_created_at: dict[str, float] = {}


def _sweep_expired() -> None:
    now = time.time()
    ttl = settings.session_ttl_seconds

    for token in [t for t, ts in _session_created_at.items() if now - ts > ttl]:
        sessions.pop(token, None)
        _session_created_at.pop(token, None)

    # OAuth states are short-lived by nature; a much smaller fixed window
    # (10 minutes) keeps a half-completed login flow from lingering.
    for state in [s for s, ts in _oauth_state_created_at.items() if now - ts > 600]:
        oauth_states.pop(state, None)
        _oauth_state_created_at.pop(state, None)


def _session(request: Request) -> dict[str, Any]:
    _sweep_expired()
    token = request.cookies.get("session_token")
    if not token or token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return sessions[token]


@app.get("/")
def root():
    return {"service": "DRM Agent", "status": "ok"}


@app.post("/login")
def login(username: str, password: str):
    if username != settings.ngo_username or password != settings.ngo_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _sweep_expired()

    auth_url, state, code_verifier = create_authorization_url()

    login_token = secrets.token_urlsafe(32)

    oauth_states[state] = {
        "login_token": login_token,
        "code_verifier": code_verifier,
    }
    _oauth_state_created_at[state] = time.time()
    sessions[login_token] = {"authenticated": True, "gmail_credentials": None}
    _session_created_at[login_token] = time.time()
    return {"message": "Credentials accepted. Authorize Gmail next.", "google_auth_url": auth_url}


@app.get("/auth/google/callback")
def google_callback(code: str, state: str):
    _sweep_expired()
    oauth_data = oauth_states.pop(state, None)
    _oauth_state_created_at.pop(state, None)

    if not oauth_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state"
        )

    login_token = oauth_data["login_token"]
    code_verifier = oauth_data["code_verifier"]

    credentials = exchange_code(
        code,
        state,
        code_verifier,
    )
    sessions[login_token]["gmail_credentials"] = encrypt_credentials(credentials.to_json())
    # Land the browser back in the SPA (not FastAPI's Swagger UI) so its
    # init() flow can detect `connected=1`, show the "Gmail connected"
    # banner, and resume at the right step.
    response = RedirectResponse(url="/app/?connected=1")
    response.set_cookie(
        "session_token", login_token, httponly=True,
        max_age=settings.session_ttl_seconds, samesite="lax",
    )
    return response


@app.post("/logout")
def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        sessions.pop(token, None)
        _session_created_at.pop(token, None)
    response = RedirectResponse(url="/app/")
    response.delete_cookie("session_token")
    return response


@app.get("/session")
def get_session(request: Request):
    """Non-throwing session-state check for the frontend's init() flow.

    Unlike `_session()` (used by the data endpoints), this never raises
    401 — an unauthenticated visitor just gets
    {authenticated: false, gmail_connected: false} so the SPA can decide
    which onboarding step to show without treating "not logged in yet"
    as an error.
    """
    _sweep_expired()
    token = request.cookies.get("session_token")
    session = sessions.get(token) if token else None
    if not session:
        return {"authenticated": False, "gmail_connected": False}
    return {
        "authenticated": bool(session.get("authenticated")),
        "gmail_connected": bool(session.get("gmail_credentials")),
    }


@app.post("/donors/upload")
async def upload_donors(request: Request, file: UploadFile = File(...)):
    _session(request)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    try:
        records = load_donors_from_csv(await file.read())
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    donor_records.clear()
    donor_records.extend(records)
    return {"count": len(donor_records), "donors": [d.model_dump() for d in donor_records]}


@app.get("/donors")
def list_donors(request: Request):
    _session(request)
    return {"count": len(donor_records), "donors": [d.model_dump() for d in donor_records]}


@app.post("/donors/process")
def process_donors(request: Request):
    session = _session(request)
    if not session.get("gmail_credentials"):
        raise HTTPException(status_code=400, detail="Gmail authorization is required")
    if not donor_records:
        raise HTTPException(status_code=400, detail="Upload donor CSV first")

    from google.oauth2.credentials import Credentials
    decrypted_json = decrypt_credentials(session["gmail_credentials"])
    credentials = Credentials.from_authorized_user_info(
        __import__("json").loads(decrypted_json)
    )
    gmail = GmailService(
        credentials,
        max_threads=settings.max_threads_per_donor,
        max_messages_per_thread=settings.max_messages_per_thread,
    )
    results = [process_donor(gmail, donor) for donor in donor_records]
    return {"count": len(results), "results": results}


# Serve the SPA frontend at /app/ (and /app/index.html). Mounted after every
# API route above so it can never shadow them — StaticFiles with html=True
# serves index.html for directory-style requests, which is what the
# frontend's history.replaceState({}, '', '/app/') and
# window.location.href = '/app/' calls expect to land on.
_STATIC_APP_DIR = Path(__file__).resolve().parent/ "web"
app.mount("/app", StaticFiles(directory=_STATIC_APP_DIR, html=True), name="app")