"""
Donor Relationship Agent — Backend (FastAPI)

Lightweight single-NGO auth (not multi-tenant) + CSV upload/import.

Run with:
    uvicorn main:app --reload

Endpoints:
    POST /login          -> sets a session cookie if credentials match
    POST /logout         -> clears session
    GET  /me             -> confirms whether you're logged in
    POST /donors/upload  -> upload a donor CSV (requires login)
    GET  /donors          -> list current donors (requires login)
"""

import csv
import io
import os
import secrets
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Cookie, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Donor Relationship Agent API")

# Allow the frontend (running on a different port during dev) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Config (lightweight, single-NGO) ----
# For the hackathon: one hardcoded org login. Swap for env vars before sharing the repo.
NGO_USERNAME = os.environ.get("NGO_USERNAME", "ngo_admin")
NGO_PASSWORD = os.environ.get("NGO_PASSWORD", "changeme123")

# In-memory session store: {session_token: True}
# Fine for a single-process hackathon demo. Not for production.
active_sessions: dict[str, bool] = {}

# In-memory donor store, populated by CSV upload.
donor_records: list[dict] = []

DATA_DIR = "data"
DONOR_CSV_PATH = os.path.join(DATA_DIR, "donors.csv")


# ---- Request models ----
class LoginRequest(BaseModel):
    username: str
    password: str


# ---- Load existing donor data ----
def load_donors_from_disk():
    global donor_records

    if not os.path.exists(DONOR_CSV_PATH):
        donor_records = []
        return

    try:
        with open(DONOR_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            donor_records = list(reader)
    except (OSError, csv.Error):
        donor_records = []


# Load persisted donors when the server starts
load_donors_from_disk()


# ---- Auth helpers ----
def require_login(session_token: Optional[str] = Cookie(default=None)):
    if not session_token or session_token not in active_sessions:
        raise HTTPException(status_code=401, detail="Not logged in")
    return True


# ---- Auth routes ----
@app.post("/login")
def login(credentials: LoginRequest, response: Response):
    if (
        credentials.username != NGO_USERNAME
        or credentials.password != NGO_PASSWORD
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = secrets.token_urlsafe(32)
    active_sessions[token] = True

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,  # 8 hour session
    )

    return {"message": "Logged in"}


@app.post("/logout")
def logout(
    response: Response,
    session_token: Optional[str] = Cookie(default=None),
):
    if session_token and session_token in active_sessions:
        del active_sessions[session_token]

    response.delete_cookie("session_token")

    return {"message": "Logged out"}


@app.get("/me")
def me(session_token: Optional[str] = Cookie(default=None)):
    logged_in = bool(
        session_token and session_token in active_sessions
    )

    return {"logged_in": logged_in}


# ---- Donor CSV routes ----
@app.post("/donors/upload")
async def upload_donors(
    file: UploadFile = File(...),
    _: bool = Depends(require_login),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a .csv file",
        )

    raw = await file.read()

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="CSV must be encoded as UTF-8",
        )

    reader = csv.DictReader(io.StringIO(text))
    records = list(reader)

    if not records:
        raise HTTPException(
            status_code=400,
            detail="CSV appears to be empty",
        )

    # Basic column sanity check
    required_cols = {"donor_id", "name", "email"}

    actual_cols = set(reader.fieldnames or [])
    missing = required_cols - actual_cols

    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV is missing required columns: "
                + ", ".join(sorted(missing))
            ),
        )

    global donor_records
    donor_records = records

    # Persist to disk too, so tools.py-style functions can read it later
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(
        DONOR_CSV_PATH,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=reader.fieldnames,
        )
        writer.writeheader()
        writer.writerows(records)

    return {
        "message": f"Imported {len(records)} donor records",
        "donor_count": len(records),
        "saved_to": DONOR_CSV_PATH,
    }


@app.get("/donors")
def list_donors(_: bool = Depends(require_login)):
    return {
        "donor_count": len(donor_records),
        "donors": donor_records,
    }


@app.get("/")
def root():
    return {
        "status": "Donor Relationship Agent backend is running"
    }