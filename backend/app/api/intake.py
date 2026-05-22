from fastapi import APIRouter, HTTPException
from requests import RequestException

from app.schemas.intake import IntakeRequest, IntakeResponse
from app.services.case_intake_service import run_intake

router = APIRouter()


@router.post("/intake", response_model=IntakeResponse)
def intake(payload: IntakeRequest) -> IntakeResponse:
    try:
        return run_intake(payload.messages, payload.current_facts)
    except RequestException as error:
        raise HTTPException(status_code=502, detail="LLM 문진 서비스 호출에 실패했습니다.") from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
