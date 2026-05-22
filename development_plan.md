# Caselink 개발계획서
## 서비스 구현 및 DB/RAG 파이프라인 개발 계획

| 항목 | 내용 |
| :--- | :--- |
| 기준 문서 | `prd.md` v1.2 |
| 작성일 | 2026-05-22 |
| 서비스명 | Caselink |
| 개발 목표 | 조문·사실관계 기반 대법원 판례 탐색 및 비교 MVP 구현 |

---

## 0. 개발 체크리스트

PRD v1.2와 본 개발계획서를 기준으로 구현 상태를 추적한다.

### 기반 설정

- [x] 프로젝트 디렉터리 구조 생성
- [x] Supabase pgvector 마이그레이션 작성
- [x] 핵심 테이블 마이그레이션 작성
- [x] 벡터 검색 RPC 마이그레이션 작성
- [x] 환경변수 템플릿 작성
- [x] Supabase Caselink 프로젝트 마이그레이션 적용
- [x] RAG 판단 근거 chunk 테이블 작성
- [x] Supabase advisor 경고 1차 보정

### 데이터 파이프라인

- [x] 국가법령정보 API 수집 스크립트 골격 작성
- [x] 판례 원문 정규화 스크립트 작성
- [x] 구조화 데이터 생성 스크립트 작성
- [x] `statute`, `issue`, `facts`, `combined` 임베딩 텍스트 생성 스크립트 작성
- [x] 로컬 GPU 임베딩 스크립트 골격 작성
- [x] Supabase 적재 스크립트 골격 작성
- [x] 파이프라인 실행 진입점 작성
- [x] 실제 국가법령정보 API 키로 대법원 임대차 판례 215건 수집
- [x] 실제 로컬 GPU 환경에서 1024차원 임베딩 860개 생성
- [x] 실제 Supabase 프로젝트에 샘플 데이터 적재

### Backend MVP

- [x] FastAPI 프로젝트 구조 작성
- [x] 검색 API 구현
- [x] 판례 상세 API 구현
- [x] 비교 API 구현
- [x] 피드백 API 구현
- [x] 입력 타입 판별 로직 구현
- [x] 랭킹 및 결과 그룹 분류 구현
- [x] 사용자 일반어 질의 임베딩 및 Supabase pgvector 검색 연결
- [x] Gemini 기반 사건 문진/추가 질문 API 구현
- [x] 샘플 데이터 기반 검색 fallback 구현
- [x] Supabase DB 기반 판례 조회 구현
- [x] Python/FastAPI 런타임 환경에서 API 실행 검증

### Frontend MVP

- [x] 검색 화면 구현
- [x] 추가 질문 문진 화면 구현
- [x] 결과 목록 화면 구현
- [x] 2열 비교 화면 구현
- [x] 공식 원문 링크 새 탭 열기 구현
- [x] 피드백/오류 신고 UI 구현
- [x] "반대 판례" 및 유사도 퍼센트 미노출 확인
- [x] 법률 자문이 아닌 학습 보조 목적 고지 표시

### 검증

- [x] 샘플 검색어 문서 작성
- [x] 평가 정책 문서 작성
- [x] 프론트엔드 정적 실행 확인
- [ ] 인앱 브라우저 시각 검증
- [x] 백엔드 런타임 테스트
- [x] 개발 완료 항목 체크리스트 반영

---

## 1. 개발 목표

Caselink는 사용자가 조문, 사건번호, 자연어 사건 설명을 입력하면 관련 대법원 판례를 찾고, 판례 간 사실관계·쟁점·적용조문·판단 포인트를 비교해주는 판례 탐색 보조 서비스이다.

MVP 개발의 핵심은 다음 두 흐름을 분리해 안정적으로 구현하는 것이다.

```text
데이터 파이프라인 = 판례를 수집·정규화·구조화·임베딩하여 DB에 적재
서비스 구현 = 이미 적재된 DB와 벡터를 검색하여 사용자에게 결과 제공
```

운영 백엔드는 국가법령정보 API를 직접 호출하지 않는다. 국가법령정보 API 호출과 로컬 GPU 임베딩은 모두 로컬 데이터 파이프라인에서 수행한다.

---

## 2. 전체 시스템 구조

```text
사용자
  ↓
Frontend
  ↓
Backend API
  ↓
Supabase Postgres + pgvector
  ↑
Local RAG Pipeline
  ↑
국가법령정보 API
```

### 2.1 구성 요소

| 영역 | 역할 |
| :--- | :--- |
| Frontend | 검색 입력, 결과 목록, 2열 비교 화면, 피드백 UI |
| Backend | 검색 요청 처리, 질의 구조화, 임베딩, pgvector 검색, 결과 재정렬 |
| Supabase | 판례 원문, 구조화 데이터, 임베딩 벡터, 피드백 저장 |
| Pipeline | 판례 수집, 정규화, LLM 구조화, 로컬 GPU 임베딩, DB 적재 |

### 2.2 권장 디렉터리 구조

```text
main_project_v4/
  frontend/
    src/
      app/
      components/
      lib/
      types/

  backend/
    app/
      main.py
      api/
        search.py
        precedents.py
        feedback.py
      services/
        query_parser.py
        embedding_service.py
        search_service.py
        ranking_service.py
        comparison_service.py
      db/
        supabase_client.py
      schemas/
        search.py
        precedent.py
        feedback.py

  pipelines/
    collect_precedents.py
    normalize_precedents.py
    structure_precedents.py
    build_embedding_texts.py
    embed_precedents.py
    load_to_supabase.py
    run_pipeline.py
    config.py

  supabase/
    migrations/
      001_enable_pgvector.sql
      002_create_precedent_tables.sql
      003_create_vector_search_functions.sql

  docs/
    sample_queries.md
    evaluation_policy.md
```

MVP 초반에는 파일 수를 줄여도 되지만, 서비스 코드와 파이프라인 코드는 반드시 분리한다.

---

## 3. 기술 스택

### 3.1 Frontend

| 항목 | 선택 |
| :--- | :--- |
| Framework | Next.js 또는 React |
| 배포 | Vercel |
| 주요 기능 | 검색 입력, 결과 목록, 비교 화면, 원문 링크, 피드백 |

### 3.2 Backend

| 항목 | 선택 |
| :--- | :--- |
| Framework | FastAPI |
| 배포 | Vercel Python Serverless Function 또는 별도 FastAPI 배포 |
| 주요 기능 | 검색 API, 벡터 검색, 랭킹, 비교 응답 생성 |

### 3.3 DB

| 항목 | 선택 |
| :--- | :--- |
| DB | Supabase Postgres |
| Vector DB | pgvector |
| Vector Similarity | cosine similarity |

### 3.4 Embedding

| 항목 | 선택 |
| :--- | :--- |
| 실행 위치 | 로컬 데스크톱 GPU |
| GPU 기준 | NVIDIA RTX 3070 |
| 임베딩 모델 | `intfloat/multilingual-e5-large` |
| 차원 | 1024 |
| 문서 prefix | `passage:` |
| 검색어 prefix | `query:` |

---

## 4. DB 설계

### 4.1 `precedents`

판례 원문과 기본 메타데이터를 저장한다.

```sql
create table precedents (
  id uuid primary key default gen_random_uuid(),
  case_no text not null,
  court_name text,
  decision_date date,
  case_name text,
  raw_text text not null,
  source_url text,
  source text default 'national_law_api',
  collected_at timestamptz default now(),
  created_at timestamptz default now(),
  unique (case_no, decision_date)
);
```

### 4.2 `precedent_structures`

검색과 비교에 사용할 구조화 데이터를 저장한다.

```sql
create table precedent_structures (
  id uuid primary key default gen_random_uuid(),
  precedent_id uuid not null references precedents(id) on delete cascade,
  legal_domain text,
  case_type text,
  referenced_statutes text[],
  referenced_cases text[],
  legal_issue_summary text,
  fact_summary text,
  outcome_label text,
  decision_point text,
  search_keywords text[],
  preprocess_status text default 'pending',
  llm_model text,
  prompt_version text,
  processed_at timestamptz,
  reviewed boolean default false,
  needs_review boolean default false,
  created_at timestamptz default now()
);
```

### 4.3 `precedent_embeddings`

RAG 검색용 벡터를 저장한다.

```sql
create table precedent_embeddings (
  id uuid primary key default gen_random_uuid(),
  precedent_id uuid not null references precedents(id) on delete cascade,
  embedding_type text not null check (
    embedding_type in ('statute', 'issue', 'facts', 'combined')
  ),
  embedding_model text not null,
  embedding_dimension int not null,
  content_text text not null,
  content_hash text not null,
  embedding vector(1024) not null,
  needs_regeneration boolean default false,
  created_at timestamptz default now(),
  unique (precedent_id, embedding_type, embedding_model, content_hash)
);
```

### 4.4 `search_feedbacks`

사용자 피드백과 오류 신고를 저장한다.

```sql
create table search_feedbacks (
  id uuid primary key default gen_random_uuid(),
  query_text text,
  query_type text,
  base_precedent_id uuid references precedents(id),
  compared_precedent_id uuid references precedents(id),
  is_relevant boolean,
  is_helpful boolean,
  label_issue_reported boolean default false,
  comment text,
  created_at timestamptz default now()
);
```

### 4.5 벡터 검색 함수

Supabase RPC로 호출할 검색 함수를 만든다.

```sql
create or replace function match_precedent_embeddings(
  query_embedding vector(1024),
  match_embedding_type text,
  match_embedding_model text,
  match_count int default 30
)
returns table (
  precedent_id uuid,
  embedding_type text,
  similarity float
)
language sql stable
as $$
  select
    precedent_id,
    embedding_type,
    1 - (embedding <=> query_embedding) as similarity
  from precedent_embeddings
  where embedding_type = match_embedding_type
    and embedding_model = match_embedding_model
    and needs_regeneration = false
  order by embedding <=> query_embedding
  limit match_count;
$$;
```

---

## 5. RAG 데이터 파이프라인 개발 계획

### 5.1 파이프라인 목표

로컬에서 국가법령정보 API로 대법원 판례를 수집하고, 검색에 적합한 구조화 텍스트와 임베딩 벡터를 생성해 Supabase에 적재한다.

### 5.2 파이프라인 단계

```text
1. collect
2. normalize
3. structure
4. build embedding texts
5. embed
6. load
7. validate
```

### 5.3 `collect_precedents.py`

역할:

- 국가법령정보 API 호출
- 대법원 판례 목록 수집
- 판례 상세 원문 수집
- 중복 판례 제외
- 원문과 메타데이터를 로컬 JSONL 또는 DB staging에 저장

입력:

```text
API key
검색 기간
법원 구분
페이지 크기
```

출력:

```text
data/raw/precedents_YYYYMMDD.jsonl
```

### 5.4 `normalize_precedents.py`

역할:

- HTML 태그 제거
- 깨진 문자와 중복 공백 정리
- 판시사항, 판결요지, 참조조문, 참조판례, 주문, 이유 영역 분리
- 사건번호, 선고일, 사건명 정규화

출력:

```text
data/normalized/precedents_YYYYMMDD.jsonl
```

### 5.5 `structure_precedents.py`

역할:

- LLM 또는 규칙 기반 파서로 검색용 구조화 필드 생성
- 핵심 쟁점, 사실관계, 결론 라벨, 판단 포인트 생성
- 프롬프트 버전과 모델명 기록
- 신뢰도가 낮은 결과는 `needs_review = true` 표시

구조화 결과:

```json
{
  "legal_domain": "민사",
  "case_type": "주택임대차",
  "referenced_statutes": ["주택임대차보호법 제6조"],
  "legal_issue_summary": "임대차계약의 묵시적 갱신 성립 여부",
  "fact_summary": "임대인이 갱신거절 통지를 하지 않은 상태에서 임차인이 계속 거주한 사안",
  "outcome_label": "묵시적 갱신 인정",
  "decision_point": "갱신거절 통지의 시기와 방식",
  "search_keywords": ["묵시적 갱신", "갱신거절", "임대차"]
}
```

### 5.6 `build_embedding_texts.py`

역할:

- 구조화 데이터를 바탕으로 임베딩용 텍스트 생성
- `statute`, `issue`, `facts`, `combined` 4종 생성
- 모든 문서 텍스트에 `passage:` prefix 부착
- `content_hash` 생성

예시:

```text
passage: 민사 주택임대차 사건이다.
참조조문은 주택임대차보호법 제6조이다.
핵심 쟁점은 임대차계약의 묵시적 갱신 성립 여부이다.
사실관계는 임대인이 갱신거절 통지를 하지 않은 상태에서 임차인이 계속 거주한 사안이다.
판단 포인트는 갱신거절 통지의 시기와 방식이다.
판결 결과 라벨은 묵시적 갱신 인정이다.
```

### 5.7 `embed_precedents.py`

역할:

- `intfloat/multilingual-e5-large` 모델 로드
- 로컬 GPU에서 배치 임베딩 생성
- L2 normalize
- 1024차원 벡터 생성
- 임베딩 결과를 로컬 파일 또는 DB staging에 저장

처리 원칙:

- 같은 모델로 생성한 벡터만 검색에서 비교한다.
- 모델을 변경하면 기존 벡터와 혼용하지 않고 재생성한다.
- `content_hash`가 기존과 같으면 재임베딩하지 않는다.

### 5.8 `load_to_supabase.py`

역할:

- `precedents` 적재
- `precedent_structures` 적재
- `precedent_embeddings` 적재
- 실패 건과 중복 건 로그 기록

### 5.9 `run_pipeline.py`

역할:

- 전체 파이프라인 실행 진입점
- 단계별 실행 옵션 제공

예시 명령:

```bash
python pipelines/run_pipeline.py --from collect --to load --limit 100
python pipelines/run_pipeline.py --from embed --to load --only-missing
```

---

## 6. Backend 개발 계획

### 6.1 API 목록

#### `POST /api/search`

사용자 입력을 받아 관련 판례를 검색한다.

요청:

```json
{
  "query": "주택임대차보호법 제6조",
  "query_type": "auto"
}
```

응답:

```json
{
  "query": "주택임대차보호법 제6조",
  "detected_query_type": "statute",
  "related_statutes": ["주택임대차보호법 제6조"],
  "base_precedent": {},
  "results": {
    "statute_related": [],
    "fact_similar": [],
    "different_decision_point": []
  }
}
```

#### `GET /api/precedents/{id}`

판례 상세와 구조화 데이터를 조회한다.

#### `POST /api/compare`

기준 판례와 비교 판례의 비교 설명을 생성하거나 조회한다.

#### `POST /api/feedback`

검색 결과 피드백과 오류 신고를 저장한다.

### 6.2 Query Parser

역할:

- 입력이 조문인지, 사건번호인지, 자연어인지 판별
- 조문 입력 예: `주택임대차보호법 제6조`
- 사건번호 입력 예: `2020다12345`
- 자연어 입력이면 관련 조문 후보, 사건유형, 키워드 추출

출력:

```json
{
  "query_type": "statute",
  "statutes": ["주택임대차보호법 제6조"],
  "case_no": null,
  "natural_query": null,
  "keywords": ["묵시적 갱신"]
}
```

### 6.3 Embedding Service

역할:

- 사용자 검색어에 `query:` prefix 부착
- 검색 질의를 임베딩
- MVP에서는 백엔드에서 같은 모델을 로드하거나, 별도 임베딩 서버/API를 사용한다.

주의:

- 운영 백엔드가 Vercel Serverless라면 `intfloat/multilingual-e5-large`를 직접 로드하기 어려울 수 있다.
- 이 경우 질의 임베딩만 처리하는 별도 경량 임베딩 API 또는 사전 계산 가능한 조문 검색 우선 전략을 둔다.
- 조문 입력은 벡터 임베딩 없이도 `referenced_statutes` 필터와 `statute` 벡터 검색을 조합할 수 있다.

### 6.4 Search Service

검색 흐름:

```text
1. 입력 타입 판별
2. 조문/사건번호/자연어 검색 슬롯 생성
3. 조문이 있으면 참조조문 필터로 1차 후보 조회
4. query 임베딩 생성
5. statute / combined / issue / facts 벡터 검색
6. 후보 점수 병합
7. 구조화 데이터와 원문 메타데이터 조회
8. 결과 그룹 분류
```

### 6.5 Ranking Service

초기 점수:

```text
최종 점수 =
  참조조문 일치 25%
+ statute 벡터 유사도 20%
+ combined 벡터 유사도 25%
+ issue 벡터 유사도 15%
+ facts 벡터 유사도 10%
+ 사건유형 일치 5%
```

조문이 없는 자연어 검색에서는 다음처럼 조정한다.

```text
최종 점수 =
  combined 벡터 유사도 35%
+ issue 벡터 유사도 25%
+ facts 벡터 유사도 25%
+ statute 벡터 유사도 10%
+ 사건유형 일치 5%
```

### 6.6 Comparison Service

역할:

- 기준 판례와 비교 판례의 공통 조문, 공통 쟁점, 유사 사실관계, 다른 판단 포인트를 정리한다.
- LLM 설명은 검색된 구조화 데이터 안에서만 생성한다.
- 원문에 없는 사실을 추가하지 않는다.

비교 응답 필드:

```json
{
  "common_statutes": [],
  "common_issue": "",
  "similar_facts": "",
  "different_decision_point": "",
  "outcome_label_difference": "",
  "caution": "결론 라벨이 다르더라도 사실관계가 동일하다는 의미는 아닙니다."
}
```

---

## 7. Frontend 개발 계획

### 7.1 화면 구성

#### 검색 화면

- 서비스명 Caselink
- 조문/사건번호/자연어 통합 검색창
- 예시 검색어
  - `주택임대차보호법 제6조`
  - `2020다12345`
  - `임대인이 갱신거절 통지를 하지 않은 임대차 사건`
- 법률 자문이 아니라 판례 탐색 보조 서비스라는 짧은 안내

#### 결과 화면

- 감지된 입력 유형
- 관련 조문 또는 관련 조문 후보
- 관련 판례 목록
- 사실관계 유사 판례 목록
- 판단 포인트가 다른 판례 목록
- 원문 링크

#### 비교 화면

- 좌측 기준 판례
- 우측 비교 판례
- 공통 조문
- 공통 쟁점
- 유사한 사실관계
- 다르게 판단된 포인트
- 결론 라벨 차이
- 공식 원문 링크
- 도움 됨/오류 신고 버튼

### 7.2 UI 원칙

- 유사도 퍼센트는 노출하지 않는다.
- "반대 판례"라는 표현은 사용하지 않는다.
- "판단 포인트가 다른 판례", "결론 라벨이 다른 비교 판례"로 표시한다.
- 원문 링크는 항상 새 탭으로 연다.
- 결과가 없으면 검색어 또는 조문을 바꿔보라는 안내를 제공한다.

---

## 8. 개발 단계별 일정

### Phase 1. 기반 설정

산출물:

- 프로젝트 디렉터리 생성
- Supabase 프로젝트 준비
- pgvector 활성화
- DB 마이그레이션 작성
- 환경변수 템플릿 작성

완료 기준:

- Supabase에 4개 핵심 테이블 생성
- 벡터 검색 RPC 함수 동작 확인

### Phase 2. 샘플 데이터 파이프라인

산출물:

- 국가법령정보 API 수집 스크립트
- 정규화 스크립트
- 구조화 스크립트
- 임베딩 텍스트 생성 스크립트
- 로컬 GPU 임베딩 스크립트
- Supabase 적재 스크립트

완료 기준:

- 샘플 판례 20~50건 적재
- 판례 1건당 4개 임베딩 생성
- pgvector 검색 결과 확인

### Phase 3. Backend MVP

산출물:

- FastAPI 프로젝트
- 검색 API
- 판례 상세 API
- 비교 API
- 피드백 API
- 랭킹 로직

완료 기준:

- 조문 입력 검색 가능
- 사건번호 입력 검색 가능
- 자연어 입력 검색 가능
- 결과 그룹 분류 가능

### Phase 4. Frontend MVP

산출물:

- 검색 화면
- 결과 목록 화면
- 2열 비교 화면
- 원문 링크
- 피드백/오류 신고 UI

완료 기준:

- 사용자가 검색부터 원문 확인까지 이어갈 수 있음
- 비교 화면에서 공통점과 차이점 확인 가능

### Phase 5. 품질 검수 및 튜닝

산출물:

- 샘플 검색어 목록
- 검색 결과 검수표
- 라벨 오류 기록
- 가중치 조정 기록

완료 기준:

- 조문 기반 검색 결과가 안정적으로 관련 판례를 반환
- 사실관계 유사 판례가 납득 가능한 수준으로 정렬
- 오류 신고와 피드백 저장 정상 동작

---

## 9. 테스트 계획

### 9.1 파이프라인 테스트

- API 수집 결과에 사건번호, 선고일, 원문이 있는지 확인
- 정규화 후 원문이 비어 있지 않은지 확인
- 참조조문이 정상 추출되는지 확인
- 구조화 결과에 필수 필드가 있는지 확인
- 임베딩 차원이 1024인지 확인
- 같은 `content_hash`는 중복 임베딩하지 않는지 확인

### 9.2 검색 테스트

테스트 입력:

```text
주택임대차보호법 제6조
묵시적 갱신
임대인이 갱신거절 통지를 하지 않은 사건
2020다12345
```

확인 항목:

- 조문 입력 시 관련 조문 판례가 우선 노출되는가
- 사건번호 입력 시 기준 판례가 정확히 잡히는가
- 자연어 입력 시 관련 조문 후보가 표시되는가
- 원문 링크가 새 탭으로 열리는가
- 유사도 퍼센트가 노출되지 않는가
- "반대 판례"라는 표현이 노출되지 않는가

### 9.3 비교 테스트

- 공통 조문이 정확히 표시되는지 확인
- 사실관계 유사 설명이 원문에 없는 내용을 추가하지 않는지 확인
- 결론 라벨이 다른 경우에도 "사실관계가 동일한데 결론이 반대"라고 설명하지 않는지 확인
- 공식 원문 확인 권고가 표시되는지 확인

---

## 10. 리스크 및 대응

| 리스크 | 대응 |
| :--- | :--- |
| 판례 원문 정규화 품질이 낮음 | 구역 분리 실패 건을 `needs_review`로 표시하고 수동 검수 |
| LLM 구조화 결과가 부정확함 | 프롬프트 버전 저장, 샘플 검수, 재처리 가능하게 설계 |
| 결론 라벨이 과도하게 단순화됨 | 라벨을 검색 보조 정보로만 사용하고 원문 확인 권고 표시 |
| Vercel에서 임베딩 모델 실행이 어려움 | 질의 임베딩용 별도 API 또는 조문 기반 검색 우선 전략 사용 |
| 벡터 검색 결과가 조문과 무관하게 나옴 | 참조조문 일치와 `statute` 임베딩 가중치 강화 |
| 사용자가 법률 자문으로 오해함 | 모든 결과 화면에 학습 보조 목적과 원문 확인 고지 표시 |

---

## 11. MVP 완료 기준

MVP는 아래 조건을 만족하면 완료로 본다.

- 로컬 파이프라인으로 샘플 대법원 판례를 수집하고 Supabase에 적재할 수 있다.
- 판례 1건당 `statute`, `issue`, `facts`, `combined` 임베딩이 생성된다.
- 조문 입력으로 관련 판례를 검색할 수 있다.
- 사건번호 입력으로 기준 판례를 잡고 관련 판례를 찾을 수 있다.
- 자연어 입력으로 사실관계가 유사한 판례를 찾을 수 있다.
- 기준 판례와 비교 판례를 2열 화면에서 비교할 수 있다.
- 모든 결과에 공식 원문 링크가 제공된다.
- 피드백과 오류 신고가 저장된다.
- 서비스 화면에서 법률 자문으로 오해될 표현을 사용하지 않는다.

---

## 12. 우선 구현 순서

1. Supabase 마이그레이션 작성
2. 샘플 판례 20~50건 수집
3. 정규화 및 구조화 스크립트 구현
4. `intfloat/multilingual-e5-large` 로컬 GPU 임베딩 구현
5. pgvector 검색 함수 구현
6. FastAPI 검색 API 구현
7. 랭킹 및 결과 그룹 분류 구현
8. 프론트 검색 화면 구현
9. 결과 목록 및 비교 화면 구현
10. 피드백/오류 신고 구현
11. 샘플 검색어로 품질 검수
12. Vercel 배포 구조 정리
