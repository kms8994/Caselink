from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    query_text: str | None = None
    query_type: str | None = None
    base_precedent_id: str | None = None
    compared_precedent_id: str | None = None
    is_relevant: bool | None = None
    is_helpful: bool | None = None
    label_issue_reported: bool = False
    comment: str | None = None


class FeedbackResponse(BaseModel):
    ok: bool
    message: str

