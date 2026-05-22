from typing import Any, Literal

from pydantic import BaseModel, Field

IntakeStatus = Literal["need_more_info", "ready"]


class IntakeMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class IntakeRequest(BaseModel):
    messages: list[IntakeMessage] = Field(min_length=1)
    current_facts: dict[str, Any] = Field(default_factory=dict)


class IntakeResponse(BaseModel):
    status: IntakeStatus
    domain: str
    confidence: float = Field(ge=0, le=1)
    extracted_facts: dict[str, Any]
    missing_fields: list[str]
    follow_up_questions: list[str]
    search_query: str | None = None
    related_statutes: list[str] = []
    embedding_targets: list[str] = []
