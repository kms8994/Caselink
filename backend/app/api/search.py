from fastapi import APIRouter, HTTPException

from app.schemas.search import CompareRequest, CompareResponse, SearchRequest, SearchResponse
from app.services.comparison_service import compare
from app.services.search_service import search

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search_precedents(payload: SearchRequest) -> SearchResponse:
    return search(payload.query, payload.query_type)


@router.post("/compare", response_model=CompareResponse)
def compare_precedents(payload: CompareRequest) -> CompareResponse:
    result = compare(payload.base_precedent_id, payload.compared_precedent_id)
    if result is None:
        raise HTTPException(status_code=404, detail="판례를 찾을 수 없습니다.")
    return result

