import csv
import io
import logging

from drmagent.config import settings
from drmagent.drm.agent import create_drm_agent, classify_and_plan
from drmagent.drm.approval import apply_human_approval_policy
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord
from drmagent.profile.service import build_donor_profile
from drmagent.state_store import DonorStateStore, is_in_cooldown

logger = logging.getLogger(__name__)

_state_store = DonorStateStore(settings.donor_state_path)


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


def _process_donor_inner(gmail: GmailService, donor: DonorRecord) -> dict:
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
    # The hard policy recalculates it, and — whenever it fires — also
    # overrides plan.action and the fields a future execution step would
    # otherwise read (see drm/approval.py for why).
    # ------------------------------------------------------------------
    plan, approval_reasons = apply_human_approval_policy(
        profile=profile,
        classification=classification,
        plan=plan,
        conversations=conversations,
        donation_threshold=settings.donation_approval_threshold,
        confidence_threshold=settings.min_confidence_threshold,
    )

    # ------------------------------------------------------------------
    # 4. Cooldown check: don't repeat a low-stakes outbound action
    # (Thank You / Outreach) for the same donor within the cooldown
    # window just because a later run re-derived the same action.
    # Human Review and Follow-Up are never suppressed this way.
    # ------------------------------------------------------------------
    donor_state = _state_store.get(donor.donor_id)
    suppressed_for_cooldown = False
    if is_in_cooldown(donor_state, plan.action, settings.action_cooldown_days):
        suppressed_for_cooldown = True
        plan.consistency_notes.append(
            f"Action '{plan.action}' was suppressed: it was already taken for "
            f"this donor within the last {settings.action_cooldown_days} day(s)."
        )
        original_action = plan.action
        plan.action = "Wait"
        plan.recommended_action = f"No action ({original_action} already sent recently)."
        plan.next_step = "None; wait for the cooldown window to pass."
        plan.message_type = None
        plan.message_context = None
    else:
        _state_store.record_action(donor.donor_id, plan.action)
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
    # 5. Return planning + approval information.
    #
    # Execution Agent will be connected in a later step.
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
        "cooldown_suppressed": suppressed_for_cooldown,
    }


def process_donor(gmail: GmailService, donor: DonorRecord) -> dict:
    """Process a single donor, never letting an unexpected failure here take
    down the rest of a batch run. Any unhandled error is itself treated as a
    reason for human review rather than as a crash."""

    try:
        return _process_donor_inner(gmail, donor)
    except Exception as exc:  # noqa: BLE001 - deliberate top-level fail-safe
        logger.exception("process_donor failed for donor_id=%s", donor.donor_id)
        return {
            "donor": donor.model_dump(),
            "conversation_count": 0,
            "profile": None,
            "classification": None,
            "plan": {
                "donor_id": donor.donor_id,
                "action": "Human Review",
                "objective": "Recover from an unhandled processing error.",
                "recommended_action": "Escalate to a human before any donor communication.",
                "next_step": "Human approval required.",
                "requires_human_approval": True,
                "consistency_notes": [f"Unhandled error during processing: {exc}"],
            },
            "approval": {
                "requires_human_approval": True,
                "reason": [f"Unhandled processing error: {exc.__class__.__name__}: {exc}"],
            },
            "cooldown_suppressed": False,
        }
