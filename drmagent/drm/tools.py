from strands import tool


@tool
def draft_message(donor_id: str, message_type: str, context: str) -> str:
    """Create a message-drafting request for a downstream communication service.

    This prototype intentionally returns a request payload rather than sending email.
    """
    return f"Draft requested for donor={donor_id}, type={message_type}. Context: {context}"


@tool
def flag_for_human(donor_id: str, reason: str, recommendation: str) -> str:
    """Create a human-review escalation payload."""
    return f"Human review required for {donor_id}: {reason}. Recommendation: {recommendation}"


@tool
def update_donor(donor_id: str, status: str, next_action_date: str | None = None) -> str:
    """Return a donor-state update request for persistence by the API layer."""
    return f"Update requested for {donor_id}: status={status}, next_action_date={next_action_date}"
