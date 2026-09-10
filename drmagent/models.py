from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DonorRecord(BaseModel):
    donor_id: str
    name: Optional[str] = None
    email: str


class EmailMessage(BaseModel):
    id: str
    thread_id: str
    subject: str = ""
    sender: str = ""
    recipients: list[str] = Field(default_factory=list)
    date: str = ""
    timestamp: int = 0
    body_text: str = ""


class DonorConversation(BaseModel):
    donor_id: str
    donor_email: str
    thread_id: str
    subject: str = ""
    messages: list[EmailMessage] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    donor_id: str
    key_points: list[str] = Field(default_factory=list)
    requests: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    relationship_signals: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DonorProfile(BaseModel):
    donor_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    donation_context: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    requests: list[str] = Field(default_factory=list)
    commitments_made_by_ngo: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    communication_summary: str = ""
    sentiment: Optional[str] = None
    relationship_signals: list[str] = Field(default_factory=list)
    last_contact_date: Optional[str] = None
    follow_up_required: bool = False
    human_review_required: bool = False
    notes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


Action = Literal["Thank You", "Outreach", "Follow-Up", "Wait", "Human Review"]


class ActionClassification(BaseModel):
    donor_id: str
    action: Action
    reason: str
    urgency: Literal["low", "medium", "high"] = "low"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ActionPlan(BaseModel):
    donor_id: str
    action: Action
    objective: str
    recommended_action: str
    next_step: str
    message_type: Optional[str] = None
    message_context: Optional[str] = None
    requires_human_approval: bool = False
    due_date: Optional[str] = None
