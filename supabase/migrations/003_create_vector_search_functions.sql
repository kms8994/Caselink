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

