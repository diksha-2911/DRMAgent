from strands import Agent
from strands.models.openai import OpenAIModel

from drmagent.config import settings
from drmagent.llm_utils import INJECTION_GUARD, safe_structured_output
from drmagent.models import ConversationSummary, DonorProfile


def _model(model_id: str) -> OpenAIModel:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required")
    return OpenAIModel(
        client_args={"api_key": settings.groq_api_key, "base_url": settings.groq_base_url},
        model_id=model_id,
        params={"temperature": 0.0, "max_tokens": 2500, "stream_options": None},
    )


# NOTE: Classification and planning used to also be defined here
# (create_classification_agent / create_planning_agent / classify() /
# plan()), as a second, independently-maintained copy of the same policy
# implemented in drmagent/drm/agent.py. The orchestrator only ever called
# the drm/agent.py version, so this module's copy was dead code that could
# silently drift out of sync with the real decision logic (e.g. a new
# Human Review trigger added to one prompt and forgotten in the other).
# It has been removed. drmagent/drm/agent.py is now the single source of
# truth for classification + planning.


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
            "and duplicated quoted replies where possible.\n"
            + INJECTION_GUARD
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
            "interests, sentiment, and unresolved items. Set `confidence` honestly: lower it "
            "whenever the summary is sparse, ambiguous, or you had to leave fields empty for "
            "lack of information — a downstream deterministic policy uses this value to decide "
            "whether a human should review this donor instead of relying on your output alone.\n"
            + INJECTION_GUARD
        ),
    )


def _low_confidence_summary(donor_id: str, exc: Exception) -> ConversationSummary:
    return ConversationSummary(
        donor_id=donor_id,
        summary=f"Automated consolidation failed ({exc.__class__.__name__}); needs manual review.",
        confidence=0.0,
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


def _low_confidence_profile(donor_id: str, exc: Exception) -> DonorProfile:
    return DonorProfile(
        donor_id=donor_id,
        human_review_required=True,
        notes=[f"Automated profile extraction failed ({exc.__class__.__name__}); needs manual review."],
        confidence=0.0,
    )


def consolidate(agent: Agent, donor_id: str, conversation_text: str) -> ConversationSummary:
    prompt = f"Donor ID: {donor_id}\n\nConversation:\n{conversation_text}"
    return safe_structured_output(
        agent,
        ConversationSummary,
        prompt,
        fallback_factory=lambda exc: _low_confidence_summary(donor_id, exc),
    )


def extract(agent: Agent, summary: ConversationSummary, donor_name: str | None, donor_email: str) -> DonorProfile:
    prompt = (
        f"Donor ID: {summary.donor_id}\nName: {donor_name or ''}\nEmail: {donor_email}\n\n"
        f"Conversation summary:\n{summary.model_dump_json(indent=2)}"
    )
    return safe_structured_output(
        agent,
        DonorProfile,
        prompt,
        fallback_factory=lambda exc: _low_confidence_profile(summary.donor_id, exc),
    )
