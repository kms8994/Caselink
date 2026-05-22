from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.feedback import router as feedback_router
from app.api.intake import router as intake_router
from app.api.precedents import router as precedents_router
from app.api.search import router as search_router

app = FastAPI(
    title="Caselink API",
    description="조문·사실관계 기반 대법원 판례 검색 및 비교 MVP API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router, prefix="/api", tags=["search"])
app.include_router(intake_router, prefix="/api", tags=["intake"])
app.include_router(precedents_router, prefix="/api", tags=["precedents"])
app.include_router(feedback_router, prefix="/api", tags=["feedback"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "caselink"}
