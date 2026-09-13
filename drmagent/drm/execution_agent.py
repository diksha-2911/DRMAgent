from strands import Agent
from strands.models.openai import OpenAIModel

from drmagent.config import settings
from drmagent.models import (
    ActionClassification,
    ActionPlan,
    DonorProfile,
    EmailDraft,
    ExecutionResult,
)


def _model() -> OpenAIModel:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required")

    return OpenAIModel(
        client_args={
            "api_key": settings.groq_api_key,
            "base_url": settings.groq_base_url,
        },
        model_id=settings.planning_model,
        params={
            "temperature": 0.2,
            "max_tokens": 2000,
            "stream_options": None,
        },
    )


EXECUTION_PROMPT = """
You are the execution agent for a Donor Relationship Management system.

The planning agent has already determined the donor action and created
an action plan.

Your responsibility is to execute the approved plan by preparing the
required communication.

You MUST follow the approved action plan.

Do not change the action selected by the planning agent.

For email actions:
- Create a professional email draft.
- Use the donor's name and email from the supplied profile.
- Use the supplied Gmail conversation context to understand what the
  donor is responding to.
- Follow the objective and recommended_action from the plan.
- Keep the response appropriate to the existing conversation.
- Do not invent facts, attachments, dates, promises, bank details,
  payment information, or other information not present in the context.
- Do not claim that an attachment has been provided unless an actual
  attachment is supplied by the application.
- Do not expose internal planning, classification, approval, or system
  information to the donor.
- Do not claim that an action has already happened when it has not.

For this stage, generate the email draft only.
The application will handle the actual Gmail operation later.

Return the result using the required structured output schema.
"""


def create_execution_agent() -> Agent:
    return Agent(
        model=_model(),
        system_prompt=EXECUTION_PROMPT,
    )


def execute_plan(
    agent: Agent,
    profile: DonorProfile,
    classification: ActionClassification,
    plan: ActionPlan,
    thread_id: str,
    message_id: str,
    conversation_context: str,
) -> ExecutionResult:

    execution_input = f"""
DONOR PROFILE:
{profile.model_dump_json(indent=2)}

CLASSIFICATION:
{classification.model_dump_json(indent=2)}

APPROVED ACTION PLAN:
{plan.model_dump_json(indent=2)}

GMAIL CONTEXT:
thread_id: {thread_id}
message_id: {message_id}

CONVERSATION CONTEXT:
{conversation_context}

Prepare the email required by the approved action plan.
"""

    email_draft = agent.structured_output(
        EmailDraft,
        execution_input,
    )

    return ExecutionResult(
        status="drafted",
        thread_id=thread_id,
        message_id=message_id,
        email=email_draft,
    )