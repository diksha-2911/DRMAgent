from strands import Agent
from strands.models.openai import OpenAIModel

from drmagent.config import settings
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
"""


def create_drm_agent() -> Agent:
    return Agent(model=_model(), system_prompt=DRM_PROMPT)


def classify_and_plan(agent: Agent, profile: DonorProfile) -> tuple[ActionClassification, ActionPlan]:
    classification = agent.structured_output(
        ActionClassification,
        f"Classify this donor:\n{profile.model_dump_json(indent=2)}",
    )
    plan = agent.structured_output(
        ActionPlan,
        f"PROFILE:\n{profile.model_dump_json(indent=2)}\n\nACTION:\n{classification.model_dump_json(indent=2)}",
    )
    return classification, plan
