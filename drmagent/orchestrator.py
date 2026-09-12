import csv
import io

from drmagent.config import settings
from drmagent.drm.agent import create_drm_agent, classify_and_plan
from drmagent.drm.approval import apply_human_approval_policy
from drmagent.gmail.service import GmailService
from drmagent.models import DonorRecord
from drmagent.profile.service import build_donor_profile


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
    # 4. Return planning + approval information.
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
    }