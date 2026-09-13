import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from drmagent.config import settings
from drmagent.gmail.auth import create_authorization_url, exchange_code
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord
from drmagent.orchestrator import load_donors_from_csv, process_donor, process_incoming_message
from drmagent.worker.gmail_watcher import GmailWatcher

app = FastAPI(title="DRM Agent", version="1.0.0")

# Demo-only in-memory state. Replace with a database/secure session store in production.
sessions: dict[str, dict[str, Any]] = {}
# oauth_states: dict[str, str] = {}
oauth_states: dict[str, dict[str, str]] = {}
donor_records: list[DonorRecord] = []
gmail_watcher: GmailWatcher | None = None

logger = logging.getLogger(__name__)


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

    # auth_url, state = create_authorization_url()
    # login_token = secrets.token_urlsafe(32)
    # oauth_states[state] = login_token
    auth_url, state, code_verifier = create_authorization_url()

    login_token = secrets.token_urlsafe(32)

    oauth_states[state] = {
        "login_token": login_token,
        "code_verifier": code_verifier,
    }
    sessions[login_token] = {"authenticated": True, "gmail_credentials": None}
    return {"message": "Credentials accepted. Authorize Gmail next.", "google_auth_url": auth_url}

async def handle_new_gmail_message(
    gmail: GmailService,
    message: dict[str, Any],
) -> None:
    """
    Handle a newly detected Gmail message.

    2D.1:
    Only log the message.

    Later steps will replace this with the actual autonomous
    donor workflow.
    """

    logger.info(
        "Autonomous Gmail event received: "
        "message_id=%s thread_id=%s sender=%s subject=%s",
        message["message_id"],
        message["thread_id"],
        message["sender"],
        message["subject"],
    )

    if not donor_records:
        logger.warning(
            "Autonomous Gmail event ignored: no donor records "
            "have been uploaded."
        )
        return

    try:
        result = await process_incoming_message(
            gmail=gmail,
            message=message,
            donor_records=donor_records,
        )

        if result is None:
            return

        logger.info(
            "Autonomous DRM result: donor=%s action=%s "
            "approval_required=%s",
            result["donor"]["donor_id"],
            result["classification"]["action"],
            result["approval"]["requires_human_approval"],
        )

    except Exception:
        logger.exception(
            "Autonomous processing failed for Gmail message %s",
            message["message_id"],
        )


@app.get("/auth/google/callback")
async def google_callback(code: str, state: str):
    # login_token = oauth_states.pop(state, None)
    # if not login_token:
    #     raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    # credentials = exchange_code(code, state)
    oauth_data = oauth_states.pop(state, None)

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
    # sessions[login_token]["gmail_credentials"] = credentials.to_json()
    # response = RedirectResponse(url="/docs")

    sessions[login_token]["gmail_credentials"] = credentials.to_json()

    print("DEBUG: Gmail OAuth completed successfully")
    print(f"DEBUG: login_token={login_token}")

    global gmail_watcher

    # Start/restart the autonomous Gmail watcher using the
    # credentials that were just authorized.
    if gmail_watcher:
        await gmail_watcher.stop()

    gmail = GmailService(
        credentials,
        max_threads=settings.max_threads_per_donor,
        max_messages_per_thread=settings.max_messages_per_thread,
    )
    print("DEBUG: Creating GmailService")
    # gmail_watcher = GmailWatcher(
    #     gmail_service=gmail,
    #     on_message=handle_new_gmail_message,
    #     poll_interval=settings.gmail_poll_interval_seconds,
    # )

    async def on_gmail_message(
        message: dict[str, Any],
    ) -> None:
        await handle_new_gmail_message(
            gmail,
            message,
    )

    gmail_watcher = GmailWatcher(
        gmail_service=gmail,
        on_message=on_gmail_message,
        poll_interval=settings.gmail_poll_interval_seconds,
    )

    print("DEBUG: Starting GmailWatcher")
    await gmail_watcher.start()

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


@app.post("/test/gmail-reply")
def test_gmail_reply(request: Request):
    session = _session(request)

    if not session.get("gmail_credentials"):
        raise HTTPException(
            status_code=400,
            detail="Gmail authorization is required",
        )

    from google.oauth2.credentials import Credentials
    credentials = Credentials.from_authorized_user_info(
        __import__("json").loads(session["gmail_credentials"])
    )

    gmail = GmailService(
        credentials,
        max_threads=settings.max_threads_per_donor,
        max_messages_per_thread=settings.max_messages_per_thread,
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
