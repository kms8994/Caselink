create table if not exists precedent_reason_chunks (
  id uuid primary key default gen_random_uuid(),
  precedent_id uuid not null references precedents(id) on delete cascade,
  chunk_type text not null check (
    chunk_type in ('issue', 'facts', 'reasoning', 'decision_point', 'outcome')
  ),
  chunk_text text not null,
  source_section text,
  referenced_statutes text[],
  embedding_model text,
  embedding_dimension int,
  embedding vector(1024),
  content_hash text not null,
  needs_review boolean default false,
  created_at timestamptz default now(),
  unique (precedent_id, chunk_type, content_hash)
);

create index if not exists idx_precedent_structures_precedent_id
  on precedent_structures(precedent_id);

create index if not exists idx_precedent_embeddings_precedent_id_type
  on precedent_embeddings(precedent_id, embedding_type);

create index if not exists idx_reason_chunks_precedent_id_type
  on precedent_reason_chunks(precedent_id, chunk_type);

create index if not exists idx_precedent_embeddings_vector
  on precedent_embeddings using hnsw (embedding vector_cosine_ops);

create index if not exists idx_reason_chunks_vector
  on precedent_reason_chunks using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

alter table precedents enable row level security;
alter table precedent_structures enable row level security;
alter table precedent_embeddings enable row level security;
alter table precedent_reason_chunks enable row level security;
alter table search_feedbacks enable row level security;
alter table collection_requests enable row level security;

create policy "service role can manage precedents"
  on precedents for all
  to service_role
  using (true)
  with check (true);

create policy "service role can manage precedent structures"
  on precedent_structures for all
  to service_role
  using (true)
  with check (true);

create policy "service role can manage precedent embeddings"
  on precedent_embeddings for all
  to service_role
  using (true)
  with check (true);

create policy "service role can manage precedent reason chunks"
  on precedent_reason_chunks for all
  to service_role
  using (true)
  with check (true);

create policy "service role can manage search feedbacks"
  on search_feedbacks for all
  to service_role
  using (true)
  with check (true);

create policy "service role can manage collection requests"
  on collection_requests for all
  to service_role
  using (true)
  with check (true);

create or replace function match_precedent_reason_chunks(
  query_embedding vector(1024),
  match_embedding_model text,
  match_count int default 10
)
returns table (
  chunk_id uuid,
  precedent_id uuid,
  chunk_type text,
  chunk_text text,
  source_section text,
  similarity float
)
language sql stable
as $$
  select
    id as chunk_id,
    precedent_id,
    chunk_type,
    chunk_text,
    source_section,
    1 - (embedding <=> query_embedding) as similarity
  from precedent_reason_chunks
  where embedding is not null
    and embedding_model = match_embedding_model
  order by embedding <=> query_embedding
  limit match_count;
$$;

