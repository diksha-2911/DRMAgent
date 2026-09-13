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

====================
STRICT INFORMATION POLICY
====================

The email must be grounded ONLY in information explicitly provided in:

1. DONOR PROFILE
2. CLASSIFICATION
3. APPROVED ACTION PLAN
4. CONVERSATION CONTEXT

These are the ONLY sources of facts that you may use.

You MUST NOT:
- invent facts about the NGO
- invent programs, initiatives, campaigns, projects, events, or activities
- invent dates, deadlines, statistics, amounts, outcomes, achievements,
  promises, commitments, or future plans
- invent donation/payment/bank information
- assume that the NGO has performed an action unless the supplied context
  explicitly says it has happened
- assume that an attachment exists
- add information merely because it would make the email sound more complete
  or professional
- introduce specific details that are not present in the supplied context

If a piece of information is not explicitly available in the supplied
context, DO NOT include it.

When there is not enough information to state a specific fact, use a
general statement or omit that information entirely.

Do not infer organizational facts from the donor's intent.

====================
EMAIL RULES
====================

For email actions:

- Create a professional email draft.
- Use the donor's name and email from the supplied profile when available.
- Use the supplied Gmail conversation context to understand what the donor
  is responding to.
- Follow the objective and recommended_action from the plan.
- Keep the response concise and directly relevant to the current action.
- Preserve the meaning and facts of the existing conversation.
- Do not introduce unrelated information.
- Do not create additional initiatives, recommendations, updates, or
  opportunities unless explicitly present in the supplied context.
- Do not invent facts, attachments, dates, promises, bank details,
  payment information, or other information not present in the context.
- Do not claim that an attachment has been provided unless an actual
  attachment is supplied by the application.
- Do not claim that an action has already happened when it has not.
- Do not expose internal planning, classification, approval, or system
  information to the donor.

====================
ACTION-SPECIFIC BEHAVIOR
====================

Follow-Up:
Respond specifically to the pending request or unresolved item identified
in the supplied context. Do not introduce unrelated information.

Thank You:
Thank the donor for their message, support, feedback, or other explicitly
stated interaction. Do not turn a thank-you response into an update,
outreach message, fundraising request, or announcement.

Outreach:
Introduce the NGO or relevant engagement only using information explicitly
provided in the supplied context. Do not invent organizational programs,
achievements, initiatives, statistics, or other facts.

Wait:
Do not create an email unless the approved action plan explicitly requires
one.

Human Review:
This action must not be executed. Do not generate a donor-facing email.

====================
OUTPUT
====================

Generate the email draft only for an approved executable action.

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