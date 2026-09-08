from typing import Optional
from pydantic import BaseModel, Field

from strands import Agent
from strands.models.openai import OpenAIModel

# from app.core.config import settings
# from dotenv import load_dotenv
# load_dotenv()

class EcommerceExtraction(BaseModel):
    """
    Structured information extracted from ecommerce emails.

    Fields are nullable/optional because the model must only return
    information explicitly present in the email text.
    """

    sender: Optional[str] = None
    sender_type: Optional[str] = None

    order_id: Optional[str] = None
    order_date: Optional[str] = None

    item: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[str] = None
    currency: Optional[str] = None

    delivery_status: Optional[str] = None
    expected_delivery_date: Optional[str] = None
    actual_delivery_date: Optional[str] = None

    tracking_number: Optional[str] = None
    carrier: Optional[str] = None

    delivery_address: Optional[str] = None

    payment_status: Optional[str] = None
    payment_method: Optional[str] = None

    return_status: Optional[str] = None
    refund_status: Optional[str] = None
    refund_amount: Optional[str] = None

    notes: Optional[str] = None

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )


EXTRACTION_SYSTEM_PROMPT = """
You are an information extraction engine.

Your task is to extract structured information from ecommerce email
history supplied as a chronological text blob.

The emails may contain order confirmations, shipping updates,
delivery notifications, invoices, returns, refunds, cancellations,
or other ecommerce-related information.

IMPORTANT RULES:

1. Only extract information explicitly present in the email text.
2. Never invent or infer an order ID, item, amount, date, tracking
   number, carrier, or status.
3. If a field cannot be determined, return null.
4. Preserve values such as order IDs and tracking numbers exactly
   as they appear when possible.
5. If multiple emails describe the same order, use the latest
   information for the current status.
6. Prefer the most recent explicitly stated delivery status.
7. If an actual delivery date is explicitly present, use it for
   actual_delivery_date.
8. Use expected_delivery_date only for an explicitly stated
   expected/promised delivery date.
9. If there are multiple products in the same order and they can
   be represented as a single item description, combine them in
   the item field. Do not invent product information.
10. The notes field should contain only useful additional information
    explicitly present in the emails.
11. confidence must be between 0 and 1 and should reflect how much
    reliable structured information was found.

The input may contain multiple emails from the same sender and
multiple emails belonging to the same thread. Use the chronological
context to understand status changes.

For example, if an order confirmation says:
"Order #123 placed for Shoes"

and a later email says:
"Your order #123 has been delivered"

then the final delivery_status should be "delivered".

Return only data supported by the supplied email text.
"""


def create_extraction_agent():
    """Create the Strands agent used for structured extraction."""

    model = OpenAIModel(
        client_args={
            "api_key": "u0MJYSIOeXSSCG8kAiAEXgNpd0YY2yI0yvg6KCEB",
            "base_url": "https://api.cohere.ai/compatibility/v1",
        },
        model_id="command-a-03-2025",
        params={
            "max_tokens": 1500,
            "temperature": 0.0,
            "stream_options": None,
        },
    )

    return Agent(
        model=model,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )


def extract_ecommerce_data(combined_text: str) -> EcommerceExtraction:
    """
    Extract structured ecommerce information from consolidated
    email text using a Strands Agent structured output.

    Args:
        combined_text: Chronological email text produced by the
                       Gmail consolidation step.

    Returns:
        EcommerceExtraction containing the extracted fields.
    """

    if not combined_text or not combined_text.strip():
        return EcommerceExtraction(
            confidence=0.0,
            notes="No email history available."
        )

    agent = create_extraction_agent()

    try:
        result = agent.structured_output(
            EcommerceExtraction,
            f"""
Email history:

{combined_text}
"""
        )

        return result

    except Exception as e:
        print(f"Extraction failed: {e}")

        return EcommerceExtraction(
            confidence=0.0,
            notes="Extraction failed; needs manual review."
        )


if __name__ == "__main__":
    # Example consolidated text.
    # In your application, replace this with the value returned
    # by consolidate_messages() from the Gmail service.

    combined_text = """
--- Thread: Your Order Confirmation ---

[2026-09-05] From: Myntra Updates <updates@myntra.com>
Your order #MYN123456 has been confirmed.

Item: Nike Air Max Shoes
Quantity: 1
Amount: INR 4,999

Expected delivery: 10 September 2026.

--- Thread: Your Order Has Been Delivered ---

[2026-09-08] From: Myntra Updates <updates@myntra.com>
Your order #MYN123456 has been delivered.

Delivered on 8 September 2026.
Tracking number: TRK987654321.
Carrier: Delhivery.
"""

    extracted_data = extract_ecommerce_data(combined_text)

    print("\nEXTRACTED DATA")
    print("=" * 70)
    print(extracted_data.model_dump_json(indent=2))
