from strands import tool


@tool
def draft_message(
    donor_id: str,
    message_type: str,
    context: str,
) -> str:
    """
    Create a personalized donor communication draft.

    Args:
        donor_id: Donor receiving the message.
        message_type: Type of message such as thank_you,
                      outreach, or reengagement.
        context: Relevant donor context to use.
    """

    return (
        f"Draft requested for donor {donor_id}. "
        f"Type: {message_type}. "
        f"Context: {context}"
    )