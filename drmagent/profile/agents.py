from strands import Agent
from strands.models.openai import OpenAIModel

from drmagent.config import settings
from drmagent.models import ActionClassification, ActionPlan, ConversationSummary, DonorProfile


def _model(model_id: str) -> OpenAIModel:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required")
    return OpenAIModel(
        client_args={"api_key": settings.groq_api_key, "base_url": settings.groq_base_url},
        model_id=model_id,
        params={"temperature": 0.0, "max_tokens": 2500, "stream_options": None},
    )


def create_consolidation_agent() -> Agent:
    return Agent(
        model=_model(settings.consolidation_model),
        system_prompt=(
            "You are a donor communication consolidation agent. "
            "Turn chronological email messages into a concise factual summary. "
            "Identify key points, donor requests, commitments made by the NGO, "
            "unresolved items, sentiment, and relationship signals. "
            "Never invent facts. Preserve dates, amounts, names, and commitments "
            "when explicitly stated. Ignore signatures, disclaimers, tracking text, "
            "and duplicated quoted replies where possible."
        ),
    )


def create_extraction_agent() -> Agent:
    return Agent(
        model=_model(settings.extraction_model),
        system_prompt=(
            "You extract a structured donor profile from a factual conversation summary. "
            "Only use information supported by the supplied summary. Missing information "
            "must remain null, false, or an empty list as appropriate. Do not infer sensitive "
            "personal attributes. Preserve explicit requests, commitments, donation context, "
            "interests, sentiment, and unresolved items."
        ),
    )


def create_classification_agent() -> Agent:
    return Agent(
        model=_model(settings.classification_model),
        system_prompt=(
            "You classify the single next donor relationship action from a structured donor profile. "
            "Choose exactly one: Thank You, Outreach, Follow-Up, Wait, Human Review. "

            "IMPORTANT: Use the following decision rules in this order: "

            "1. Human Review: Use for major gifts, complaints, sensitive requests, "
            "or ambiguous/high-risk cases. "

            "2. Follow-Up: Use when the donor has an explicit pending request, "
            "question, unresolved item, or when the NGO has made a commitment "
            "that remains unresolved. "

            "3. Thank You: Use when the donor is expressing gratitude, appreciation, "
            "thanks, or positive acknowledgement of the NGO's communication, support, "
            "work, report, donation, or assistance, and there is no new request or "
            "unresolved item requiring action. "

            "4. Outreach: Use for proactive NGO engagement with a prospective or existing "
            "donor when there is no higher-priority action. Outreach means the NGO is "
            "initiating engagement; it must NOT be selected merely because the donor "
            "communication is positive, relationship-oriented, or mentions interest. "

            "5. Wait: Use when no action is currently needed. "

            "CRITICAL DISTINCTION: "
            "A donor saying 'thank you', 'I appreciate your work', 'thank you for the report', "
            "'I am grateful', or similar expressions of appreciation is Thank You, not Outreach. "

            "For example: "
            "DONOR: 'Thank you for sharing the impact report. I really appreciate the "
            "transparency and all the work you are doing.' "
            "ACTION: Thank You. "

            "Another example: "
            "DONOR: 'Thank you for the update. The report was very helpful.' "
            "ACTION: Thank You. "

            "Outreach should instead represent a proactive communication initiated by the NGO, "
            "especially when there is no existing donor conversation or the donor is a "
            "prospective donor. "

            "Do not invent missing facts. "
            "Use only information supported by the supplied donor profile. "
            "The selected action must be exactly one of the five allowed options."
        ),
    )


def create_planning_agent() -> Agent:
    return Agent(
        model=_model(settings.planning_model),
        system_prompt=(
            "You create an operational donor action plan from a donor profile and a classified action. "
            "Keep the plan concise and executable. Never send communication yourself. For Human Review, "
            "make approval the next step. For communication actions, provide a message type and factual "
            "context for a later drafting tool. Do not invent facts or commitments."
        ),
    )


def consolidate(agent: Agent, donor_id: str, conversation_text: str) -> ConversationSummary:
    return agent.structured_output(
        ConversationSummary,
        f"Donor ID: {donor_id}\n\nConversation:\n{conversation_text}",
    )


def extract(agent: Agent, summary: ConversationSummary, donor_name: str | None, donor_email: str) -> DonorProfile:
    return agent.structured_output(
        DonorProfile,
        f"Donor ID: {summary.donor_id}\nName: {donor_name or ''}\nEmail: {donor_email}\n\nConversation summary:\n{summary.model_dump_json(indent=2)}",
    )


def classify(agent: Agent, profile: DonorProfile) -> ActionClassification:
    return agent.structured_output(
        ActionClassification,
        f"Classify the next action for this donor:\n{profile.model_dump_json(indent=2)}",
    )


def plan(agent: Agent, profile: DonorProfile, classification: ActionClassification) -> ActionPlan:
    return agent.structured_output(
        ActionPlan,
        "Create the next-action plan from these inputs.\n\n"
        f"PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"CLASSIFICATION:\n{classification.model_dump_json(indent=2)}",
    )
