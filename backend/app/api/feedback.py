from fastapi import APIRouter

from app.schemas.feedback import FeedbackRequest, FeedbackResponse

router = APIRouter()
FEEDBACK_STORE: list[FeedbackRequest] = []


@router.post("/feedback", response_model=FeedbackResponse)
def create_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    FEEDBACK_STORE.append(payload)
    return FeedbackResponse(ok=True, message="피드백이 저장되었습니다.")

