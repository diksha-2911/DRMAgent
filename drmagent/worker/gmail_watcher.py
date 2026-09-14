import asyncio
import logging
from typing import Any, Awaitable, Callable

from drmagent.gmail.service import GmailService

logger = logging.getLogger(__name__)


class GmailWatcher:
    """
    Poll Gmail for new incoming messages.

    2D.1:
    - Detect new Gmail messages automatically.
    - Do not classify them yet.
    - Do not plan anything yet.
    - Do not send any email yet.

    Later steps will connect on_message() to the existing workflow.
    """

    def __init__(
        self,
        gmail_service: GmailService,
        on_message: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        poll_interval: int = 30,
    ) -> None:
        self.gmail_service = gmail_service
        self.on_message = on_message
        self.poll_interval = poll_interval

        self._running = False
        self._task: asyncio.Task | None = None

        # Message IDs already seen during this application run.
        self._seen_message_ids: set[str] = set()

    # async def start(self) -> None:
    #     """Start the Gmail polling worker."""

    #     if self._running:
    #         logger.info("Gmail watcher is already running.")
    #         return

    #     self._running = True

    #     # Establish the initial baseline so existing inbox messages
    #     # are not treated as new messages.
    #     await asyncio.to_thread(self._initialize_seen_messages)

    #     self._task = asyncio.create_task(self._poll_loop())

    #     logger.info(
    #         "Gmail watcher started. Poll interval: %s seconds.",
    #         self.poll_interval,
    #     )

    async def start(self) -> None:
        """Start the Gmail polling worker."""

        if self._running:
            logger.info("Gmail watcher is already running.")
            return

        print("DEBUG: GmailWatcher.start() entered")

        self._running = True

        print("DEBUG: Initializing Gmail watcher state")

        await asyncio.to_thread(self._initialize_seen_messages)

        print(
            f"DEBUG: Initial state contains "
            f"{len(self._seen_message_ids)} messages"
        )

        self._task = asyncio.create_task(self._poll_loop())

        print("DEBUG: Gmail watcher polling task created")

        logger.info(
            "Gmail watcher started. Poll interval: %s seconds.",
            self.poll_interval,
        )

    async def stop(self) -> None:
        """Stop the Gmail polling worker."""

        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._task = None

        logger.info("Gmail watcher stopped.")

    # def _initialize_seen_messages(self) -> None:
    #     """
    #     Capture the current inbox state.

    #     This prevents all old emails already present when the watcher
    #     starts from being treated as newly received emails.
    #     """

    #     try:
    #         response = (
    #             self.gmail_service.service
    #             .users()
    #             .messages()
    #             .list(
    #                 userId="me",
    #                 labelIds=["INBOX"],
    #                 maxResults=100,
    #             )
    #             .execute()
    #         )

    #         for message in response.get("messages", []):
    #             self._seen_message_ids.add(message["id"])

    #         logger.info(
    #             "Gmail watcher initialized with %s existing messages.",
    #             len(self._seen_message_ids),
    #         )

    #     except Exception:
    #         logger.exception(
    #             "Failed to initialize Gmail watcher message state."
    #         )

    def _initialize_seen_messages(self) -> None:
        """
        Capture the current inbox state so existing messages aren't
        treated as new messages.
        """

        print("DEBUG: _initialize_seen_messages() entered")

        try:
            response = (
                self.gmail_service.service
                .users()
                .messages()
                .list(
                    userId="me",
                    labelIds=["INBOX"],
                    maxResults=100,
                )
                .execute()
            )

            print(
                "DEBUG: Gmail list request succeeded"
            )

            for message in response.get("messages", []):
                self._seen_message_ids.add(message["id"])

            print(
                f"DEBUG: Added {len(self._seen_message_ids)} "
                f"existing Gmail messages to seen set"
            )

        except Exception as exc:
            print(
                f"DEBUG: Gmail watcher initialization failed: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.exception(
                "Failed to initialize Gmail watcher message state."
            )

    async def _poll_loop(self) -> None:
        """Continuously poll Gmail."""

        while self._running:
            try:
                print("DEBUG: Gmail watcher polling...")
                await self.check_for_new_messages()

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception("Error while polling Gmail.")

            await asyncio.sleep(self.poll_interval)

    async def check_for_new_messages(self) -> None:
        """Find messages that were not present during the previous poll."""

        messages = await asyncio.to_thread(
            self._fetch_inbox_messages
        )

        print(
            f"DEBUG: Gmail returned {len(messages)} candidate new messages"
        )


        for message in messages:
            message_id = message["message_id"]

            if message_id in self._seen_message_ids:
                continue

            self._seen_message_ids.add(message_id)

            print(
                f"DEBUG: NEW MESSAGE -> "
                f"message_id={message['message_id']} "
                f"thread_id={message['thread_id']} "
                f"sender={message['sender']} "
                f"subject={message['subject']}"
            )

            if self.on_message:
                await self.on_message(message)

    def _fetch_inbox_messages(self) -> list[dict[str, Any]]:
        """Fetch recent inbox messages with basic metadata."""

        response = (
            self.gmail_service.service
            .users()
            .messages()
            .list(
                userId="me",
                labelIds=["INBOX"],
                maxResults=100,
            )
            .execute()
        )

        gmail_messages = response.get("messages", [])

        print(
            f"DEBUG: Gmail inbox currently contains "
            f"{len(gmail_messages)} messages"
        )


        messages: list[dict[str, Any]] = []

        for item in response.get("messages", []):
            message_id = item["id"]

            print(
                f"DEBUG: Checking Gmail message {message_id} "
                f"(already_seen={message_id in self._seen_message_ids})"
            )

            # We don't need to fetch metadata for messages we already know.
            if message_id in self._seen_message_ids:
                continue

            raw_message = (
                self.gmail_service.service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=[
                        "From",
                        "To",
                        "Subject",
                        "Date",
                    ],
                )
                .execute()
            )

            payload = raw_message.get("payload", {})
            headers = payload.get("headers", [])

            messages.append(
                {
                    "message_id": message_id,
                    "thread_id": raw_message.get("threadId"),
                    "sender": self.gmail_service._header(
                        headers,
                        "From",
                    ),
                    "subject": self.gmail_service._header(
                        headers,
                        "Subject",
                    ),
                    "date": self.gmail_service._header(
                        headers,
                        "Date",
                    ),
                }
            )

        return messages