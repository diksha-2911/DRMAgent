# tools/donor_tools.py

from strands import tool

DONORS = {
    "D001": {
        "donor_id": "D001",
        "name": "Sarah",
        "email": "sarah@example.com",
        "total_donated": 12500,
        "last_donation_date": "2026-08-20",
        "last_contact_date": "2026-08-21",
        "status": "active",
    },

    "D002": {
        "donor_id": "D002",
        "name": "John",
        "email": "john@example.com",
        "total_donated": 500,
        "last_donation_date": "2026-09-05",
        "last_contact_date": "2026-08-01",
        "status": "active",
    },

    "D003": {
        "donor_id": "D003",
        "name": "Emily",
        "email": "emily@example.com",
        "total_donated": 2500,
        "last_donation_date": "2026-05-01",
        "last_contact_date": "2026-05-15",
        "status": "active",
    },

    "D004": {
        "donor_id": "D004",
        "name": "Michael",
        "email": "michael@example.com",
        "total_donated": 1500,
        "last_donation_date": "2026-06-01",
        "last_contact_date": "2026-08-20",
        "status": "active",
    },

    "D005": {
        "donor_id": "D005",
        "name": "David",
        "email": "david@example.com",
        "total_donated": 3000,
        "last_donation_date": "2026-09-05",
        "last_contact_date": "2026-09-05",
        "status": "active",
    },

    "D006": {
        "donor_id": "D006",
        "name": "Lisa",
        "email": "lisa@example.com",
        "total_donated": 2000,
        "last_donation_date": "2026-08-20",
        "last_contact_date": "2026-08-25",
        "status": "active",
    },
}

DONOR_HISTORY = {
    "D001": {
        "donations": [
            {
                "amount": 12500,
                "date": "2026-08-20"
            }
        ],
        "communications": [
            {
                "date": "2026-08-21",
                "type": "thank_you",
                "notes": "Thank-you acknowledgment sent."
            }
        ]
    },

    "D002": {
        "donations": [
            {
                "amount": 500,
                "date": "2026-09-05"
            }
        ],
        "communications": []
    },

    "D003": {
        "donations": [
            {
                "amount": 2500,
                "date": "2026-05-01"
            }
        ],
        "communications": [
            {
                "date": "2026-05-15",
                "type": "outreach",
                "notes": "Initial outreach sent."
            }
        ]
    },

    "D004": {
        "donations": [
            {
                "amount": 1500,
                "date": "2026-06-01"
            }
        ],
        "communications": [
            {
                "date": "2026-08-20",
                "type": "follow_up",
                "notes": "Donor requested a follow-up next week."
            }
        ]
    },

    "D005": {
        "donations": [
            {
                "amount": 3000,
                "date": "2026-09-05"
            }
        ],
        "communications": [
            {
                "date": "2026-09-05",
                "type": "thank_you",
                "notes": "Thank-you message sent."
            }
        ]
    },

    "D006": {
        "donations": [
            {
                "amount": 2000,
                "date": "2026-08-20"
            }
        ],
        "communications": [
            {
                "date": "2026-08-25",
                "type": "complaint",
                "notes": "Donor complained about a previous interaction."
            }
        ]
    }
}

@tool
def get_donor(donor_id: str) -> dict:
    """
    Retrieve the complete current state of a donor.

    Args:
        donor_id: Unique donor identifier.
    """

    donor = DONORS.get(donor_id)

    if donor is None:
        return {
            "error": f"Donor {donor_id} not found"
        }

    return donor

@tool
def get_donor_history(donor_id: str) -> dict:
    """
    Retrieve previous donations and communication history for a donor.
    """

    history = DONOR_HISTORY.get(donor_id)

    if history is None:
        return {
            "error": f"History for donor {donor_id} not found"
        }

    return history

@tool
def update_donor(
    donor_id: str,
    status: str,
    next_action_date: str,
) -> str:
    """
    Update the donor's relationship state.
    """

    # Update CSV/database

    return f"Updated donor {donor_id}"

# tools/communication.py

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

    # Initially this can just return structured data.
    # Later the agent itself can generate the final copy.

    return "Draft created"

# tools/escalation.py

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
    """

    # Store escalation in your data layer

    return f"Donor {donor_id} flagged for human review."

