import json
import secrets
from typing import Any
import hashlib
import base64
import secrets

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from drmagent.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "openid",
    "https://www.googleapis.com/auth/userinfo.email",]


def _client_config() -> dict[str, Any]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }




def create_authorization_url() -> tuple[str, str, str]:
    state = secrets.token_urlsafe(32)

    code_verifier = secrets.token_urlsafe(64)

    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
    )

    flow.redirect_uri = settings.google_redirect_uri

    url, _ = flow.authorization_url(
        access_type="offline",
        # include_granted_scopes="true",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )

    return url, state, code_verifier


# def create_authorization_url() -> tuple[str, str]:
#     state = secrets.token_urlsafe(32)
#     flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
#     flow.redirect_uri = settings.google_redirect_uri
#     url, _ = flow.authorization_url(
#         access_type="offline",
#         include_granted_scopes="true",
#         prompt="consent",
#     )
#     return url, state


# def exchange_code(code: str, state: str) -> Credentials:
#     flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
#     flow.redirect_uri = settings.google_redirect_uri
#     flow.fetch_token(code=code)
#     return flow.credentials


# def create_authorization_url() -> tuple[str, str, str]:
#     state = secrets.token_urlsafe(32)
#     code_verifier = secrets.token_urlsafe(64)

#     flow = Flow.from_client_config(
#         _client_config(),
#         scopes=SCOPES,
#         state=state,
#     )
#     flow.redirect_uri = settings.google_redirect_uri

#     url, _ = flow.authorization_url(
#         access_type="offline",
#         include_granted_scopes="true",
#         prompt="consent",
#         code_challenge_method="S256",
#         code_verifier=code_verifier,
#     )

#     return url, state, code_verifier


def exchange_code(code: str, state: str, code_verifier: str) -> Credentials:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
    )
    flow.redirect_uri = settings.google_redirect_uri

    flow.fetch_token(
        code=code,
        code_verifier=code_verifier,
    )

    return flow.credentials
