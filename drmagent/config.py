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
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
    )
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv(
        "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
    )
    consolidation_model: str = os.getenv(
        "CONSOLIDATION_MODEL", "openai/gpt-oss-20b"
    )
    extraction_model: str = os.getenv(
        "EXTRACTION_MODEL", "openai/gpt-oss-120b"
    )
    classification_model: str = os.getenv(
        "CLASSIFICATION_MODEL", "openai/gpt-oss-20b"
    )
    planning_model: str = os.getenv(
        "PLANNING_MODEL", "openai/gpt-oss-120b"
    )
    max_threads_per_donor: int = int(os.getenv("MAX_THREADS_PER_DONOR", "20"))
    max_messages_per_thread: int = int(os.getenv("MAX_MESSAGES_PER_THREAD", "30"))
    max_conversation_chars: int = int(os.getenv("MAX_CONVERSATION_CHARS", "50000"))


settings = Settings()
