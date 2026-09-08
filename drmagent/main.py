import os.path
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


from extraction_service import extract_ecommerce_data
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

SENDER_ID = "updates@myntra.com"


import os.path
import base64
import re

from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

SENDER_ID = "updates@myntra.com"

# Maximum number of individual messages to retrieve
MAX_MESSAGES = 5

# Maximum size of consolidated text
MAX_CHARS = 30000


def get_gmail_service():
    """Authenticate the user and return an authorized Gmail service."""

    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_header(headers, name):
    """Get a specific email header."""

    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]

    return ""


def decode_body(data):
    """Decode Gmail's base64url encoded body."""

    if not data:
        return ""

    return base64.urlsafe_b64decode(data).decode(
        "utf-8",
        errors="ignore"
    )


def html_to_text(html):
    """
    Convert HTML email content to clean plain text.

    Removes:
    - CSS/style content
    - JavaScript
    - HTML tags
    - HTML entities

    Preserves:
    - Text content
    - Basic line breaks
    """

    soup = BeautifulSoup(html, "html.parser")

    # Remove styling and non-visible content completely.
    for tag in soup(["style", "script", "head", "noscript"]):
        tag.decompose()

    # Convert common HTML elements into readable line breaks.
    for tag in soup.find_all(["br", "p", "div", "tr", "li", "h1", "h2", "h3"]):
        tag.append("\n")

    # Extract only visible text
    text = soup.get_text(separator=" ", strip=True)

    # Decode HTML entities
    # BeautifulSoup already handles most entities, but this
    # also cleans up any remaining encoded content.
    text = text.replace("\xa0", " ")

    # Remove excessive whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # Normalize excessive newlines
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


def get_email_body(payload):
    """
    Extract the text content from an email.

    Preference:
    1. text/plain
    2. text/html converted to clean plain text
    """

    html_body = None

    # -----------------------------------------------------
    # Direct body
    # -----------------------------------------------------

    body_data = payload.get("body", {}).get("data")

    if body_data:

        mime_type = payload.get("mimeType", "")

        decoded = decode_body(body_data)

        if mime_type == "text/plain":
            return decoded.strip()

        if mime_type == "text/html":
            html_body = decoded

    # -----------------------------------------------------
    # Multipart email
    # -----------------------------------------------------

    for part in payload.get("parts", []):

        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")

        # Prefer plain text
        if mime_type == "text/plain" and body_data:
            return decode_body(body_data).strip()

        # Save HTML as fallback
        if mime_type == "text/html" and body_data:
            html_body = decode_body(body_data)

        # Recursively inspect nested multipart sections
        if part.get("parts"):

            body = get_email_body(part)

            if body:
                return body

    # -----------------------------------------------------
    # Convert HTML to plain text if text/plain isn't available
    # -----------------------------------------------------

    if html_body:
        return html_to_text(html_body)

    return ""


def get_last_5_messages(service, sender):
    """
    Retrieve the last 5 individual Gmail messages from a sender.

    This retrieves messages, not threads.
    """

    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=f"from:{sender}",
            maxResults=MAX_MESSAGES
        )
        .execute()
    )

    message_refs = response.get("messages", [])

    messages = []

    for message_ref in message_refs:

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_ref["id"],
                format="full"
            )
            .execute()
        )

        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        subject = get_header(headers, "Subject")
        sender_header = get_header(headers, "From")
        recipient = get_header(headers, "To")
        date = get_header(headers, "Date")

        body = get_email_body(payload)

        if not body:
            body = message.get("snippet", "")

        timestamp = int(
            message.get("internalDate", "0")
        )

        messages.append({
            "id": message["id"],
            "thread_id": message.get("threadId"),
            "subject": subject,
            "from": sender_header,
            "to": recipient,
            "date": date,
            "body_text": body,
            "timestamp": timestamp,
        })

    return messages


def consolidate_messages(sender, messages):
    """
    Flatten the retrieved messages into one chronological
    text blob labeled by thread/subject.

    Based on the provided consolidation logic.
    """

    if not messages:
        return ""

    blocks = []

    # Sort messages oldest-first for readable chronology
    sorted_messages = sorted(
        messages,
        key=lambda message: message["timestamp"]
    )

    for message in sorted_messages:

        subject = message["subject"] or "No subject"
        body_text = message["body_text"]

        if not body_text:
            continue

        block_lines = [
            f"--- Thread: {subject} ---"
        ]

        date_str = message["date"] or "unknown date"

        block_lines.append(
            f"[{date_str}] From: {message['from']}\n"
            f"{body_text}"
        )

        blocks.append(
            "\n\n".join(block_lines)
        )

    combined = "\n\n".join(blocks)

    # Keep extraction input bounded
    if len(combined) > MAX_CHARS:
        combined = (
            combined[:MAX_CHARS]
            + "\n\n[...truncated...]"
        )

    return combined


def main():

    service = get_gmail_service()

    # -----------------------------------------------------
    # Retrieve last 5 individual messages
    # -----------------------------------------------------

    messages = get_last_5_messages(
        service,
        SENDER_ID
    )

    print("\nLAST 5 MESSAGES")
    print("=" * 70)

    if not messages:
        print(f"No messages found from {SENDER_ID}")
        return

    for index, message in enumerate(messages, start=1):

        print(f"\nMESSAGE {index}")
        print("-" * 70)

        print(f"Thread ID: {message['thread_id']}")
        print(f"From:      {message['from']}")
        print(f"To:        {message['to']}")
        print(f"Subject:   {message['subject']}")
        print(f"Date:      {message['date']}")

        print("\nBody:")
        print(message["body_text"][:2000])

    # -----------------------------------------------------
    # Consolidate messages
    # -----------------------------------------------------

    combined_text = consolidate_messages(
        SENDER_ID,
        messages
    )

    print("\n\nCONSOLIDATED TEXT")
    print("=" * 70)
    print(combined_text)


    # -----------------------------------------------------
    # Extract structured ecommerce data using Strands
    # -----------------------------------------------------

    extracted_data = extract_ecommerce_data(
        combined_text
    )

    print("\n\nEXTRACTED DATA")
    print("=" * 70)

    print(
        extracted_data.model_dump_json(
            indent=2
        )
    )


if __name__ == "__main__":
    main()
