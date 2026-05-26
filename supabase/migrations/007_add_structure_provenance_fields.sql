alter table precedent_structures
  add column if not exists summary_source text default 'rules'
    check (summary_source in ('rules', 'llm', 'human')),
  add column if not exists review_status text default 'unreviewed'
    check (review_status in ('unreviewed', 'auto_checked', 'human_reviewed')),
  add column if not exists confidence_score numeric,
  add column if not exists evidence_spans jsonb default '{}'::jsonb,
  add column if not exists source_text_hash text,
  add column if not exists structured_at timestamptz default now();

alter table precedent_reason_chunks
  add column if not exists summary_source text default 'rules'
    check (summary_source in ('rules', 'llm', 'human')),
  add column if not exists review_status text default 'unreviewed'
    check (review_status in ('unreviewed', 'auto_checked', 'human_reviewed')),
  add column if not exists evidence_text text;

create index if not exists idx_precedent_structures_review_status
  on precedent_structures(review_status);

create index if not exists idx_precedent_structures_summary_source
  on precedent_structures(summary_source);
