create index if not exists idx_search_feedbacks_base_precedent_id
  on search_feedbacks(base_precedent_id);

create index if not exists idx_search_feedbacks_compared_precedent_id
  on search_feedbacks(compared_precedent_id);

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
set search_path = public
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
set search_path = public
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

