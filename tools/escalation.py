from strands import tool


@tool
def flag_for_human(
    donor_id: str,
    reason: str,
    recommendation: str,
) -> str:
    """
    Flag a donor for human review when autonomous action
    would be inappropriate.

    Args:
        donor_id: Unique donor identifier.
        reason: Why the donor requires human intervention.
        recommendation: Suggested action for the NGO staff member.
    """

    return (
        f"Donor {donor_id} flagged for human review.\n"
        f"Reason: {reason}\n"
        f"Recommendation: {recommendation}"
    )