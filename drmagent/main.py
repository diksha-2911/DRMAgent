import secrets
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from drmagent.config import settings
from drmagent.gmail.auth import create_authorization_url, exchange_code
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord
from drmagent.orchestrator import load_donors_from_csv, process_donor

app = FastAPI(title="DRM Agent", version="1.0.0")

# Demo-only in-memory state. Replace with a database/secure session store in production.
sessions: dict[str, dict[str, Any]] = {}
oauth_states: dict[str, str] = {}
donor_records: list[DonorRecord] = []


def _session(request: Request) -> dict[str, Any]:
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

    auth_url, state = create_authorization_url()
    login_token = secrets.token_urlsafe(32)
    oauth_states[state] = login_token
    sessions[login_token] = {"authenticated": True, "gmail_credentials": None}
    return {"message": "Credentials accepted. Authorize Gmail next.", "google_auth_url": auth_url}


@app.get("/auth/google/callback")
def google_callback(code: str, state: str):
    login_token = oauth_states.pop(state, None)
    if not login_token:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    credentials = exchange_code(code, state)
    sessions[login_token]["gmail_credentials"] = credentials.to_json()
    response = RedirectResponse(url="/docs")
    response.set_cookie("session_token", login_token, httponly=True, max_age=28800, samesite="lax")
    return response


@app.post("/logout")
def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        sessions.pop(token, None)
    response = RedirectResponse(url="/")
    response.delete_cookie("session_token")
    return response


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
    credentials = Credentials.from_authorized_user_info(
        __import__("json").loads(session["gmail_credentials"])
    )
    gmail = GmailService(
        credentials,
        max_threads=settings.max_threads_per_donor,
        max_messages_per_thread=settings.max_messages_per_thread,
    )
    results = [process_donor(gmail, donor) for donor in donor_records]
    return {"count": len(results), "results": results}
