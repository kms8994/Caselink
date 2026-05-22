create table if not exists precedents (
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

create table if not exists precedent_structures (
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

create table if not exists precedent_embeddings (
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

create table if not exists search_feedbacks (
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

create table if not exists collection_requests (
  id uuid primary key default gen_random_uuid(),
  query_text text not null,
  requested_statutes text[],
  status text default 'pending',
  created_at timestamptz default now()
);

