from strands import Agent
from strands.models.openai import OpenAIModel

from drmagent.config import settings
from drmagent.llm_utils import INJECTION_GUARD, safe_structured_output
from drmagent.models import ActionClassification, ActionPlan, DonorProfile


def _model() -> OpenAIModel:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required")
    return OpenAIModel(
        client_args={"api_key": settings.groq_api_key, "base_url": settings.groq_base_url},
        model_id=settings.planning_model,
        params={"temperature": 0.1, "max_tokens": 2000, "stream_options": None},
    )


DRM_PROMPT = """
You are the final Donor Relationship Management agent.

Given a structured donor profile, determine and explain the next relationship action.
The allowed actions are exactly:
- Thank You
- Outreach
- Follow-Up
- Wait
- Human Review

Use this priority order:
1. Human Review: major gifts, complaints, sensitive requests, or ambiguous/high-risk cases.
2. Thank You: a recent donation that has not been acknowledged.
3. Follow-Up: an explicit pending donor request or an NGO commitment that remains unresolved.
4. Outreach: proactive engagement is due and there is no higher-priority action.
5. Wait: no action is currently needed.

Never invent facts. The final action must be exactly one of the five options.
Do not make the final human-approval decision. The application applies
a separate deterministic approval policy after your response.
Set requires_human_approval to false unless the plan itself explicitly
indicates Human Review.
""" + INJECTION_GUARD


def create_drm_agent() -> Agent:
    return Agent(model=_model(), system_prompt=DRM_PROMPT)


def _fallback_classification(donor_id: str, exc: Exception) -> ActionClassification:
    return ActionClassification(
        donor_id=donor_id,
        action="Human Review",
        reason=f"Automated classification failed ({exc.__class__.__name__}); routed to a human as a fail-safe.",
        urgency="high",
        confidence=0.0,
    )


def _fallback_plan(donor_id: str, exc: Exception) -> ActionPlan:
    return ActionPlan(
        donor_id=donor_id,
        action="Human Review",
        objective="Resolve an automated planning failure.",
        recommended_action="Escalate to a human before any donor communication.",
        next_step="Human approval required.",
        requires_human_approval=True,
        consistency_notes=[
            f"Automated planning failed ({exc.__class__.__name__}); routed to a human as a fail-safe."
        ],
    )


def classify_and_plan(agent: Agent, profile: DonorProfile) -> tuple[ActionClassification, ActionPlan]:
    classification = safe_structured_output(
        agent,
        ActionClassification,
        f"Classify this donor:\n{profile.model_dump_json(indent=2)}",
        fallback_factory=lambda exc: _fallback_classification(profile.donor_id, exc),
    )

    plan = safe_structured_output(
        agent,
        ActionPlan,
        (
            f"PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
            f"ACTION:\n{classification.model_dump_json(indent=2)}\n\n"
            "The `action` field of your plan MUST be exactly "
            f'"{classification.action}" (the action already classified above). '
            "Your job here is only to plan the execution of that action, not to "
            "re-decide which action it should be."
        ),
        fallback_factory=lambda exc: _fallback_plan(profile.donor_id, exc),
    )

    # The classification and planning calls are two independent generations.
    # Nothing in the model API guarantees they agree, even with the
    # instruction above, so that agreement is verified in code rather than
    # trusted. Classification is authoritative here: planning's role is to
    # execute a decision, not make one. On any mismatch, side with the
    # earlier, narrower classification call and record the discrepancy so
    # it's visible instead of silently overwritten.
    if plan.action != classification.action:
        plan.consistency_notes.append(
            f"Plan action '{plan.action}' did not match classified action "
            f"'{classification.action}'; overridden to the classified action."
        )
        plan.action = classification.action

    return classification, plan
