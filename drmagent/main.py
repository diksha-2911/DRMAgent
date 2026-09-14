import json
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.oauth2.credentials import Credentials

from drmagent.config import settings
from drmagent.gmail.auth import create_authorization_url, exchange_code
from drmagent.gmail.mock_service import MockGmailService
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord, LoginRequest
from drmagent.orchestrator import load_donors_from_csv, process_donor
from drmagent.security import decrypt_credentials, encrypt_credentials


# Sentinel used when USE_MOCK_GMAIL=true. This lets the rest of the
# application treat Gmail as connected without storing OAuth credentials.
_MOCK_CREDENTIALS_MARKER = "mock"

app = FastAPI(title="DRM Agent", version="1.0.0")

# Demo-only in-memory state. Replace with a database/secure session store
# in production.
sessions: dict[str, dict[str, Any]] = {}
oauth_states: dict[str, dict[str, str]] = {}
donor_records: list[DonorRecord] = []

_session_created_at: dict[str, float] = {}
_oauth_state_created_at: dict[str, float] = {}


def _sweep_expired() -> None:
    now = time.time()
    ttl = settings.session_ttl_seconds

    for token in [
        token
        for token, created_at in _session_created_at.items()
        if now - created_at > ttl
    ]:
        sessions.pop(token, None)
        _session_created_at.pop(token, None)

    # OAuth states are intentionally short-lived.
    for state in [
        state
        for state, created_at in _oauth_state_created_at.items()
        if now - created_at > 600
    ]:
        oauth_states.pop(state, None)
        _oauth_state_created_at.pop(state, None)


def _session(request: Request) -> dict[str, Any]:
    _sweep_expired()

    token = request.cookies.get("session_token")
    if not token or token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return sessions[token]


def _actor(session: dict[str, Any]) -> str:
    return session.get("username") or "unknown"


def _json_with_session_cookie(
    payload: dict[str, Any],
    login_token: str,
) -> JSONResponse:
    response = JSONResponse(payload)
    response.set_cookie(
        "session_token",
        login_token,
        httponly=True,
        max_age=settings.session_ttl_seconds,
        samesite="lax",
    )
    return response


@app.get("/")
def root():
    return {"service": "DRM Agent", "status": "ok"}


@app.get("/session")
def get_session(request: Request):
    """Return session state without raising 401 for logged-out visitors."""
    _sweep_expired()

    token = request.cookies.get("session_token")
    session = sessions.get(token) if token else None

    if not session:
        return {
            "authenticated": False,
            "gmail_connected": False,
        }

    return {
        "authenticated": bool(session.get("authenticated")),
        "gmail_connected": bool(session.get("gmail_credentials")),
    }


@app.post("/login")
def login(payload: LoginRequest):
    if (
        payload.username != settings.ngo_username
        or payload.password != settings.ngo_password
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _sweep_expired()

    login_token = secrets.token_urlsafe(32)

    if settings.use_mock_gmail:
        sessions[login_token] = {
            "authenticated": True,
            "gmail_credentials": _MOCK_CREDENTIALS_MARKER,
            "username": payload.username,
        }
        _session_created_at[login_token] = time.time()

        return _json_with_session_cookie(
            {
                "message": (
                    "Mock Gmail mode is active (USE_MOCK_GMAIL=true) -- "
                    "skipping real Google authorization."
                ),
                "mock": True,
            },
            login_token,
        )

    auth_url, state, code_verifier = create_authorization_url()

    oauth_states[state] = {
        "login_token": login_token,
        "code_verifier": code_verifier,
    }
    _oauth_state_created_at[state] = time.time()

    sessions[login_token] = {
        "authenticated": True,
        "gmail_credentials": None,
        "username": payload.username,
    }
    _session_created_at[login_token] = time.time()

    return {
        "message": "Credentials accepted. Authorize Gmail next.",
        "google_auth_url": auth_url,
        "mock": False,
    }


@app.get("/auth/google/callback")
def google_callback(code: str, state: str):
    _sweep_expired()

    oauth_data = oauth_states.pop(state, None)
    _oauth_state_created_at.pop(state, None)

    if not oauth_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state",
        )

    login_token = oauth_data["login_token"]
    code_verifier = oauth_data["code_verifier"]

    if login_token not in sessions:
        raise HTTPException(
            status_code=400,
            detail="Login session expired",
        )

    credentials = exchange_code(
        code,
        state,
        code_verifier,
    )

    # Store encrypted credentials; never store raw OAuth JSON in the session.
    sessions[login_token]["gmail_credentials"] = encrypt_credentials(
        credentials.to_json()
    )

    response = RedirectResponse(url="/app/?connected=1")
    response.set_cookie(
        "session_token",
        login_token,
        httponly=True,
        max_age=settings.session_ttl_seconds,
        samesite="lax",
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


@app.post("/donors/upload")
async def upload_donors(
    request: Request,
    file: UploadFile = File(...),
):
    _session(request)

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")

    try:
        records = load_donors_from_csv(await file.read())
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    donor_records.clear()
    donor_records.extend(records)

    return {
        "count": len(donor_records),
        "donors": [donor.model_dump() for donor in donor_records],
    }


@app.get("/donors")
def list_donors(request: Request):
    _session(request)

    return {
        "count": len(donor_records),
        "donors": [donor.model_dump() for donor in donor_records],
    }


def _build_gmail_service(
    session: dict[str, Any],
) -> GmailService | MockGmailService:
    """Build the Gmail client for this session."""
    if settings.use_mock_gmail:
        return MockGmailService()

    encrypted_json = session.get("gmail_credentials")
    if not encrypted_json:
        raise HTTPException(
            status_code=400,
            detail="Gmail authorization is required",
        )

    decrypted_json = decrypt_credentials(encrypted_json)
    credentials = Credentials.from_authorized_user_info(
        json.loads(decrypted_json)
    )

    return GmailService(
        credentials,
        max_threads=settings.max_threads_per_donor,
        max_messages_per_thread=settings.max_messages_per_thread,
    )


@app.post("/donors/process")
def process_donors(request: Request):
    session = _session(request)

    if not session.get("gmail_credentials"):
        raise HTTPException(
            status_code=400,
            detail="Gmail authorization is required",
        )

    if not donor_records:
        raise HTTPException(
            status_code=400,
            detail="Upload donor CSV first",
        )

    gmail = _build_gmail_service(session)

    results = [
        process_donor(gmail, donor)
        for donor in donor_records
    ]

    return {
        "count": len(results),
        "results": results,
    }


@app.post("/test/gmail-reply")
def test_gmail_reply(request: Request):
    session = _session(request)

    gmail = _build_gmail_service(session)

    # This endpoint intentionally sends a real email when real Gmail mode
    # is enabled. Use only for local testing.
    if settings.use_mock_gmail:
        raise HTTPException(
            status_code=400,
            detail="gmail-reply test requires real Gmail mode",
        )

    result = gmail.send_reply(
        thread_id="1a096798792ca6ef",
        message_id="1a0967ab3c430a11",
        to="cairen.in@gmail.com",
        subject="Re: Test Gmail Reply",
        body="""Hi,

This is a test reply from the DRMAgent Gmail execution layer.

Regards,
DRMAgent""",
    )

    return {
        "status": "sent",
        "gmail_response": result,
    }


# Serve the SPA frontend at /app/.
_STATIC_APP_DIR = Path(__file__).resolve().parent / "web"
app.mount(
    "/app",
    StaticFiles(directory=_STATIC_APP_DIR, html=True),
    name="app",
)
