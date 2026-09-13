import csv
import io
from typing import Any
from email.utils import parseaddr

from drmagent.config import settings
from drmagent.drm.agent import create_drm_agent, classify_and_plan
from drmagent.drm.approval import apply_human_approval_policy
from drmagent.drm.execution_agent import create_execution_agent, execute_plan
from drmagent.gmail.service import GmailService
from drmagent.models import (
    ActionClassification,
    ActionPlan,
    DonorRecord,
)
from drmagent.profile.service import (
    build_donor_profile,
    get_gmail_context,
    format_conversations,
)


def load_donors_from_csv(content: bytes) -> list[DonorRecord]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    required = {"donor_id", "email"}
    missing = required - set(reader.fieldnames or [])

    if missing:
        raise ValueError(
            f"Missing required CSV columns: {', '.join(sorted(missing))}"
        )

    return [
        DonorRecord(
            donor_id=(row.get("donor_id") or "").strip(),
            name=(row.get("name") or "").strip() or None,
            email=(row.get("email") or "").strip(),
        )
        for row in reader
        if (row.get("donor_id") or "").strip()
        and (row.get("email") or "").strip()
    ]

async def process_incoming_message(
    gmail: GmailService,
    message: dict[str, Any],
    donor_records: list[DonorRecord],
) -> dict | None:
    """
    Process a newly detected Gmail message through the existing
    donor relationship management workflow.

    The incoming sender is resolved against the donor CSV.
    Once resolved, the existing process_donor() workflow is reused.
    """

    sender = message.get("sender", "")
    sender_email = parseaddr(sender)[1].strip().lower()

    if not sender_email:
        print(
            "AUTONOMOUS: Could not extract sender email "
            f"from {sender!r}"
        )
        return None

    print(
        "AUTONOMOUS: Resolving incoming email from "
        f"{sender_email}"
    )

    donor = next(
        (
            record
            for record in donor_records
            if record.email.strip().lower() == sender_email
        ),
        None,
    )

    if donor is None:
        print(
            "AUTONOMOUS: No donor found in CSV for "
            f"{sender_email}. Message will not be processed."
        )
        return None

    print(
        "AUTONOMOUS: Donor resolved -> "
        f"{donor.donor_id} ({donor.email})"
    )

    result = process_donor(gmail, donor)

    print(
        "AUTONOMOUS: DRM workflow completed -> "
        f"donor={donor.donor_id} "
        f"action={result['classification']['action']} "
        f"approval_required="
        f"{result['approval']['requires_human_approval']}"
    )

    return result


def process_donor(gmail: GmailService, donor: DonorRecord) -> dict:
    # ------------------------------------------------------------------
    # 1. Build donor profile and retain the original Gmail conversations.
    # ------------------------------------------------------------------
    profile, conversations = build_donor_profile(
        gmail,
        donor,
        settings.max_conversation_chars,
    )

    # ------------------------------------------------------------------
    # 2. Classification + planning.
    #
    # If there is NO Gmail conversation history, this is deterministically
    # treated as Outreach. We do not ask the LLM to classify this case.
    # ------------------------------------------------------------------
    drm_agent = create_drm_agent()

    if not conversations:
        classification = ActionClassification(
            donor_id=donor.donor_id,
            action="Outreach",
            reason=(
                "No Gmail conversation history was found for this donor. "
                "The donor is therefore treated as a new prospective donor "
                "and requires an introductory outreach email."
            ),
            urgency="low",
            confidence=1.0,
        )

        plan = drm_agent.structured_output(
            ActionPlan,
            f"""
Create an execution plan for this NEW PROSPECTIVE DONOR.

The action is deterministically fixed as Outreach.

DONOR PROFILE:
{profile.model_dump_json(indent=2)}

ACTION:
{classification.model_dump_json(indent=2)}

Requirements:
- action MUST be Outreach.
- The objective must be to introduce the NGO and establish initial
  communication with the prospective donor.
- The recommended action must be to send an introductory email.
- Do not invent specific NGO facts.
- Do not invent programs, achievements, statistics, dates, events,
  or commitments.
- Do not request information that is not supported by the profile.
- This is a new email, not a reply.
""",
        )

        # Ensure the LLM cannot change the deterministic action.
        plan.action = "Outreach"

    else:
        classification, plan = classify_and_plan(
            drm_agent,
            profile,
        )

    # ------------------------------------------------------------------
    # 3. HARD DETERMINISTIC APPROVAL POLICY.
    # ------------------------------------------------------------------
    plan, approval_reasons = apply_human_approval_policy(
        profile=profile,
        classification=classification,
        plan=plan,
        conversations=conversations,
        donation_threshold=settings.donation_approval_threshold,
    )

    # ------------------------------------------------------------------
    # 4. HARD APPROVAL GATE.
    # ------------------------------------------------------------------
    execution = None

    if not plan.requires_human_approval:

        gmail_context = get_gmail_context(conversations)

        # --------------------------------------------------------------
        # EXISTING DONOR CONVERSATION
        # --------------------------------------------------------------
        if gmail_context:
            execution_agent = create_execution_agent()

            conversation_context = format_conversations(
                conversations,
                settings.max_conversation_chars,
            )

            execution_result = execute_plan(
                agent=execution_agent,
                profile=profile,
                classification=classification,
                plan=plan,
                thread_id=gmail_context.thread_id,
                message_id=gmail_context.message_id,
                conversation_context=conversation_context,
            )

            if (
                execution_result.status == "drafted"
                and execution_result.email is not None
            ):
                email = execution_result.email

                gmail_result = gmail.send_reply(
                    thread_id=execution_result.thread_id,
                    message_id=execution_result.message_id,
                    to=email.to,
                    subject=email.subject,
                    body=email.body,
                )

                execution = {
                    "status": "sent",
                    "thread_id": execution_result.thread_id,
                    "message_id": execution_result.message_id,
                    "gmail_message_id": gmail_result.get("id"),
                    "email": email.model_dump(),
                }

            else:
                execution = execution_result.model_dump()

        # --------------------------------------------------------------
        # NEW PROSPECTIVE DONOR
        # --------------------------------------------------------------
        else:
            # This branch is only reached when there is no Gmail history.
            # The classification above has already been deterministically
            # set to Outreach.

            execution_agent = create_execution_agent()

            execution_result = execute_plan(
                agent=execution_agent,
                profile=profile,
                classification=classification,
                plan=plan,
                thread_id=None,
                message_id=None,
                conversation_context="",
            )

            if (
                execution_result.status == "drafted"
                and execution_result.email is not None
            ):
                email = execution_result.email

                gmail_result = gmail.send_email(
                    to=email.to,
                    subject=email.subject,
                    body=email.body,
                )

                execution = {
                    "status": "sent",
                    "thread_id": None,
                    "message_id": None,
                    "gmail_message_id": gmail_result.get("id"),
                    "email": email.model_dump(),
                }

            else:
                execution = execution_result.model_dump()

    # ------------------------------------------------------------------
    # 5. Return planning + approval + execution information.
    # ------------------------------------------------------------------
    return {
        "donor": donor.model_dump(),
        "conversation_count": len(conversations),
        "profile": profile.model_dump(),
        "classification": classification.model_dump(),
        "plan": plan.model_dump(),
        "approval": {
            "requires_human_approval": plan.requires_human_approval,
            "reason": approval_reasons,
        },
        "execution": execution,
    }