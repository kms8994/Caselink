from fastapi import APIRouter, HTTPException

from app.schemas.search import PrecedentCard
from app.services.search_service import get_detail

router = APIRouter()


@router.get("/precedents/{precedent_id}", response_model=PrecedentCard)
def precedent_detail(precedent_id: str) -> PrecedentCard:
    result = get_detail(precedent_id)
    if result is None:
        raise HTTPException(status_code=404, detail="판례를 찾을 수 없습니다.")
    return result

