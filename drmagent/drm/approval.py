"""Deterministic human-approval policy for DRM actions."""

import re
from typing import Optional

from drmagent.config import settings
from drmagent.models import (
    ActionClassification,
    ActionPlan,
    DonorConversation,
    DonorProfile,
)


DEFAULT_DONATION_APPROVAL_THRESHOLD = 100_000


BANK_PAYMENT_PATTERNS = [
    r"\bbank\s+details?\b",
    r"\bbank\s+account\b",
    r"\baccount\s+(?:number|details?)\b",
    r"\baccount\s+information\b",
    r"\bifsc\b",
    r"\bupi\b",
    r"\bneft\b",
    r"\brtgs\b",
    r"\bwire\s+transfer\b",
    r"\bpayment\s+details?\b",
    r"\bpayment\s+information\b",
    r"\btransfer\s+(?:details?|information)\b",
    r"\bdonation\s+transfer\b",
]


REFUND_CANCELLATION_PATTERNS = [
    r"\brefund\b",
    r"\brefund\s+(?:my|the|this)?\s*donation\b",
    r"\bcancel\s+(?:my|the|this)?\s*donation\b",
    r"\bcancellation\s+(?:of\s+)?(?:my|the|this)?\s*donation\b",
    r"\breverse\s+(?:my|the|this)?\s*(?:donation|payment|transaction)\b",
]


TRANSACTION_DISPUTE_PATTERNS = [
    r"\bunauthori[sz]ed\s+(?:transaction|payment|charge)\b",
    r"\bunknown\s+(?:transaction|payment|charge)\b",
    r"\bwrong\s+(?:transaction|payment|charge|amount)\b",
    r"\bincorrect\s+(?:transaction|payment|charge|amount)\b",
    r"\btransaction\s+(?:dispute|error)\b",
    r"\bpayment\s+(?:dispute|error)\b",
    r"\bcharged\s+(?:twice|double)\b",
    r"\bduplicate\s+(?:transaction|payment|charge)\b",
    r"\bdispute\s+(?:a\s+)?(?:transaction|payment|charge)\b",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    normalized = " ".join(text.lower().split())

    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in patterns
    )


def _conversation_text(
    conversations: list[DonorConversation],
) -> str:
    parts: list[str] = []

    for conversation in conversations:
        if conversation.subject:
            parts.append(conversation.subject)

        for message in conversation.messages:
            if message.body_text:
                parts.append(message.body_text)

            if message.subject:
                parts.append(message.subject)

    return "\n".join(parts)


def _profile_text(profile: DonorProfile) -> str:
    parts: list[str] = [
        profile.communication_summary,
        *profile.donation_context,
        *profile.requests,
        *profile.commitments_made_by_ngo,
        *profile.unresolved_items,
        *profile.notes,
    ]

    return "\n".join(value for value in parts if value)


def _extract_inr_amounts(text: str) -> list[float]:
    """Extract INR amounts from donor communication."""

    patterns = [
        r"₹\s*([\d,]+(?:\.\d+)?)",
        r"\brs\.?\s*([\d,]+(?:\.\d+)?)",
        r"\binr\s*([\d,]+(?:\.\d+)?)",
        r"([\d,]+(?:\.\d+)?)\s*(?:rupees|inr)\b",
    ]

    amounts: list[float] = []

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            raw_amount = match.group(1).replace(",", "")

            try:
                amounts.append(float(raw_amount))
            except ValueError:
                continue

    return amounts


def _rule_donation_amount(
    text: str,
    threshold: float,
) -> Optional[str]:
    amounts = _extract_inr_amounts(text)

    if any(amount > threshold for amount in amounts):
        return (
            f"Donation/payment amount exceeds the human-approval "
            f"threshold of ₹{threshold:,.0f}."
        )

    return None


def _rule_bank_or_payment_details(
    text: str,
) -> Optional[str]:
    if _matches_any(text, BANK_PAYMENT_PATTERNS):
        return "Bank or payment details request requires human approval."

    return None


def _rule_refund_or_cancellation(
    text: str,
) -> Optional[str]:
    if _matches_any(text, REFUND_CANCELLATION_PATTERNS):
        return "Donation refund or cancellation request requires human approval."

    return None


def _rule_transaction_dispute(
    text: str,
) -> Optional[str]:
    if _matches_any(text, TRANSACTION_DISPUTE_PATTERNS):
        return "Transaction or payment dispute requires human approval."

    return None


def _rule_explicit_human_review(
    profile: DonorProfile,
    classification: ActionClassification,
    plan: ActionPlan,
) -> Optional[str]:
    if profile.human_review_required:
        return "Donor profile explicitly requires human review."

    if classification.action == "Human Review":
        return "Classification explicitly requires human review."

    if plan.action == "Human Review":
        return "Action plan explicitly requires human review."

    if plan.requires_human_approval:
        return "Action plan explicitly requests human approval."

    return None


def _rule_low_confidence(
    profile: DonorProfile,
    classification: ActionClassification,
    threshold: float,
) -> Optional[str]:
    """A model that wasn't confident is exactly the case a human should see,
    not a case that should quietly proceed as 'Wait' or 'Outreach'."""

    if profile.confidence < threshold:
        return (
            f"Donor profile confidence ({profile.confidence:.2f}) is below the "
            f"human-review threshold ({threshold:.2f})."
        )

    if classification.confidence < threshold:
        return (
            f"Action classification confidence ({classification.confidence:.2f}) "
            f"is below the human-review threshold ({threshold:.2f})."
        )

    return None


def _rule_high_urgency(
    classification: ActionClassification,
) -> Optional[str]:
    if classification.urgency == "high" and classification.action != "Human Review":
        return "Classification flagged high urgency; routed for human review as a precaution."

    return None


def determine_human_approval(
    profile: DonorProfile,
    classification: ActionClassification,
    plan: ActionPlan,
    conversations: list[DonorConversation],
    donation_threshold: float = DEFAULT_DONATION_APPROVAL_THRESHOLD,
    confidence_threshold: float = settings.min_confidence_threshold,
) -> tuple[bool, list[str]]:
    """Evaluate every deterministic approval rule.

    Returns:
        (
            requires_human_approval,
            list_of_all_triggered_reasons,
        )
    """

    text = (
        f"{_profile_text(profile)}\n"
        f"{_conversation_text(conversations)}"
    )

    reasons: list[str] = []

    # Rule 1
    reason = _rule_donation_amount(
        text,
        donation_threshold,
    )
    if reason:
        reasons.append(reason)

    # Rule 2
    reason = _rule_bank_or_payment_details(text)
    if reason:
        reasons.append(reason)

    # Rule 3
    reason = _rule_refund_or_cancellation(text)
    if reason:
        reasons.append(reason)

    # Rule 4
    reason = _rule_transaction_dispute(text)
    if reason:
        reasons.append(reason)

    # Rule 5
    reason = _rule_explicit_human_review(
        profile,
        classification,
        plan,
    )
    if reason:
        reasons.append(reason)

    # Rule 6
    reason = _rule_low_confidence(
        profile,
        classification,
        confidence_threshold,
    )
    if reason:
        reasons.append(reason)

    # Rule 7
    reason = _rule_high_urgency(classification)
    if reason:
        reasons.append(reason)

    return bool(reasons), reasons


def apply_human_approval_policy(
    profile: DonorProfile,
    classification: ActionClassification,
    plan: ActionPlan,
    conversations: list[DonorConversation],
    donation_threshold: float = DEFAULT_DONATION_APPROVAL_THRESHOLD,
    confidence_threshold: float = settings.min_confidence_threshold,
) -> tuple[ActionPlan, list[str]]:
    """Apply deterministic approval policy to the action plan.

    This is the single authoritative decision point for whether a human
    must be involved. Previously it only flipped `requires_human_approval`
    and left everything else on the plan untouched, which could leave a
    plan in a contradictory state: flagged for human approval, but still
    carrying an automated `recommended_action` / `message_context` that a
    future execution step could read and act on before a human ever looks
    at it. Now, whenever any hard rule fires, the policy also forces the
    plan's `action` to "Human Review" and clears/rewrites the fields an
    execution step would otherwise use to act autonomously.
    """

    requires_human_approval, reasons = determine_human_approval(
        profile=profile,
        classification=classification,
        plan=plan,
        conversations=conversations,
        donation_threshold=donation_threshold,
        confidence_threshold=confidence_threshold,
    )

    plan.requires_human_approval = requires_human_approval

    if requires_human_approval and plan.action != "Human Review":
        plan.consistency_notes.append(
            f"Deterministic approval policy overrode action '{plan.action}' to "
            "'Human Review' because: " + "; ".join(reasons)
        )
        plan.action = "Human Review"
        plan.recommended_action = "Escalate to a human before any donor communication."
        plan.next_step = "Human approval required."
        # Null out fields a future execution/communication step could use
        # to auto-send something despite the required-approval flag.
        plan.message_type = None
        plan.message_context = None

    return plan, reasons