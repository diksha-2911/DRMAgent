import csv
import io

from drmagent.config import settings
from drmagent.drm.agent import create_drm_agent, classify_and_plan
from drmagent.drm.approval import apply_human_approval_policy
from drmagent.drm.execution_agent import create_execution_agent, execute_plan
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord
from drmagent.profile.service import build_donor_profile, get_gmail_context, format_conversations


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
    # ------------------------------------------------------------------
    drm_agent = create_drm_agent()

    classification, plan = classify_and_plan(
        drm_agent,
        profile,
    )

    # ------------------------------------------------------------------
    # 3. HARD DETERMINISTIC APPROVAL POLICY.
    #
    # This happens after planning and before any future execution agent.
    #
    # The LLM-produced plan.requires_human_approval value is NOT trusted.
    # The hard policy recalculates and overwrites it.
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
    #
    # The Execution Agent must NEVER be called when human approval
    # is required.
    # ------------------------------------------------------------------
    execution = None

    if not plan.requires_human_approval:
        gmail_context = get_gmail_context(conversations)

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

            # execution = execute_plan(
            #     agent=execution_agent,
            #     profile=profile,
            #     classification=classification,
            #     plan=plan,
            #     thread_id=gmail_context.thread_id,
            #     message_id=gmail_context.message_id,
            #     conversation_context=conversation_context,
            # )
            # execution = execution_result.model_dump()
        else:
            execution = {
                "status": "not_executed",
                "reason": "No Gmail thread/message context available.",
            }

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