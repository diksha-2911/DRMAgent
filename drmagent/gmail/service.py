import base64
import re
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from drmagent.models import DonorConversation, EmailMessage


class GmailService:
    def __init__(self, credentials: Credentials, max_threads: int = 20, max_messages_per_thread: int = 30):
        self.service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        self.max_threads = max_threads
        self.max_messages_per_thread = max_messages_per_thread

    @staticmethod
    def _header(headers: list[dict[str, Any]], name: str) -> str:
        for header in headers:
            if header.get("name", "").lower() == name.lower():
                return header.get("value", "")
        return ""

    @staticmethod
    def _decode(data: str | None) -> str:
        if not data:
            return ""
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="ignore")

    @staticmethod
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["style", "script", "head", "noscript"]):
            tag.decompose()
        for tag in soup.find_all(["br", "p", "div", "tr", "li", "h1", "h2", "h3"]):
            tag.append("\n")
        text = soup.get_text(" ", strip=True).replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()

    @classmethod
    def _body(cls, payload: dict[str, Any]) -> str:
        plain = None
        html = None

        def walk(part: dict[str, Any]) -> None:
            nonlocal plain, html
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if data and mime == "text/plain" and plain is None:
                plain = cls._decode(data)
            elif data and mime == "text/html" and html is None:
                html = cls._decode(data)
            for child in part.get("parts", []) or []:
                walk(child)

        walk(payload)
        if plain and plain.strip():
            return plain.strip()
        if html:
            return cls._html_to_text(html)
        return ""

    def find_thread_ids(self, donor_email: str) -> list[str]:
        # Gmail braces mean OR. Searching both directions captures the full
        # donor↔NGO relationship instead of only donor-authored messages.
        query = f"{{from:{donor_email} to:{donor_email}}}"
        response = self.service.users().threads().list(
            userId="me", q=query, maxResults=self.max_threads
        ).execute()
        return [item["id"] for item in response.get("threads", [])]

    def get_thread(self, donor_id: str, donor_email: str, thread_id: str) -> DonorConversation:
        thread = self.service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()
        messages: list[EmailMessage] = []

        for raw in thread.get("messages", [])[: self.max_messages_per_thread]:
            payload = raw.get("payload", {})
            headers = payload.get("headers", [])
            date_header = self._header(headers, "Date")
            timestamp = int(raw.get("internalDate", "0"))
            if not timestamp and date_header:
                try:
                    timestamp = int(parsedate_to_datetime(date_header).timestamp() * 1000)
                except (TypeError, ValueError, OverflowError):
                    timestamp = 0

            body = self._body(payload) or raw.get("snippet", "")
            recipients = [
                value.strip()
                for value in self._header(headers, "To").split(",")
                if value.strip()
            ]
            messages.append(
                EmailMessage(
                    id=raw["id"],
                    thread_id=raw.get("threadId", thread_id),
                    subject=self._header(headers, "Subject"),
                    sender=self._header(headers, "From"),
                    recipients=recipients,
                    date=date_header,
                    timestamp=timestamp,
                    body_text=body,
                )
            )

        messages.sort(key=lambda message: message.timestamp)
        return DonorConversation(
            donor_id=donor_id,
            donor_email=donor_email,
            thread_id=thread_id,
            subject=messages[0].subject if messages else "",
            messages=messages,
        )

    def get_donor_conversations(self, donor: Any) -> list[DonorConversation]:
        return [
            self.get_thread(donor.donor_id, donor.email, thread_id)
            for thread_id in self.find_thread_ids(donor.email)
        ]
