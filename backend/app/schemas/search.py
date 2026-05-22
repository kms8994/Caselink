from typing import Literal

from pydantic import BaseModel, Field

QueryType = Literal["auto", "statute", "case_no", "natural"]
DetectedQueryType = Literal["statute", "case_no", "natural"]
ResultGroup = Literal["statute_related", "fact_similar", "different_decision_point"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    query_type: QueryType = "auto"


class ParsedQuery(BaseModel):
    query_type: DetectedQueryType
    statutes: list[str] = []
    case_no: str | None = None
    natural_query: str | None = None
    keywords: list[str] = []


class PrecedentCard(BaseModel):
    id: str
    case_no: str
    court_name: str
    decision_date: str
    case_name: str
    referenced_statutes: list[str]
    legal_issue_summary: str
    fact_summary: str
    outcome_label: str
    decision_point: str
    source_url: str
    result_label: str
    group: ResultGroup


class SearchResponse(BaseModel):
    query: str
    detected_query_type: DetectedQueryType
    related_statutes: list[str]
    base_precedent: PrecedentCard | None
    results: dict[ResultGroup, list[PrecedentCard]]
    caution: str


class CompareRequest(BaseModel):
    base_precedent_id: str
    compared_precedent_id: str


class CompareResponse(BaseModel):
    base_precedent: PrecedentCard
    compared_precedent: PrecedentCard
    common_statutes: list[str]
    common_issue: str
    similar_facts: str
    different_decision_point: str
    outcome_label_difference: str
    caution: str

