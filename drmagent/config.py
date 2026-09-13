import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ngo_username: str = os.getenv("NGO_USERNAME", "ngo_admin")
    ngo_password: str = os.getenv("NGO_PASSWORD", "change-me")

    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv(
        "GROQ_BASE_URL",
        "https://api.groq.com/openai/v1",
    )

    consolidation_model: str = os.getenv(
        "CONSOLIDATION_MODEL",
        "openai/gpt-oss-20b",
    )

    extraction_model: str = os.getenv(
        "EXTRACTION_MODEL",
        "openai/gpt-oss-120b",
    )

    classification_model: str = os.getenv(
        "CLASSIFICATION_MODEL",
        "openai/gpt-oss-20b",
    )

    planning_model: str = os.getenv(
        "PLANNING_MODEL",
        "openai/gpt-oss-120b",
    )

    max_threads_per_donor: int = int(
        os.getenv("MAX_THREADS_PER_DONOR", "20")
    )

    max_messages_per_thread: int = int(
        os.getenv("MAX_MESSAGES_PER_THREAD", "30")
    )

    max_conversation_chars: int = int(
        os.getenv("MAX_CONVERSATION_CHARS", "50000")
    )

    # Hard deterministic approval threshold.
    # Any INR donation/payment amount strictly greater than this value
    # requires human approval.
    donation_approval_threshold: float = float(
        os.getenv("DONATION_APPROVAL_THRESHOLD", "100000")
    )

    # Below this confidence, either on the extracted profile or on the
    # classification, the deterministic policy forces Human Review rather
    # than trusting a low-confidence automated decision.
    min_confidence_threshold: float = float(
        os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.5")
    )

    # A donor won't be re-sent the same low-stakes outbound action
    # (Thank You / Outreach) more than once within this many days, even if
    # the model re-derives that action on a later run.
    action_cooldown_days: int = int(
        os.getenv("ACTION_COOLDOWN_DAYS", "3")
    )

    # How many times a structured LLM call is retried before the
    # deterministic fail-safe (defaulting to Human Review) takes over.
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # Where per-donor action state is persisted for cooldown checks.
    donor_state_path: str = os.getenv(
        "DONOR_STATE_PATH", "data/donor_action_state.json"
    )

    # Symmetric key (Fernet, urlsafe base64, 32 bytes) used to encrypt Gmail
    # OAuth credentials while they sit in the in-memory session store. If
    # unset, a key is generated at process start (sessions won't survive a
    # restart either way in this in-memory demo store, so that's acceptable
    # for now, but a persistent deployment MUST set SESSION_ENCRYPTION_KEY
    # explicitly so old encrypted sessions stay decryptable).
    session_encryption_key: str = os.getenv("SESSION_ENCRYPTION_KEY", "")

    # Idle session / OAuth-state timeout, in seconds. Entries older than
    # this are swept from the in-memory stores.
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "28800"))


settings = Settings()