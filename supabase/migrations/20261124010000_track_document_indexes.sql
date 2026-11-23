begin;

create table public.document_indexes (
  document_id text primary key check (document_id ~ '^[0-9a-f]{64}$'),
  embedding_model text not null check (btrim(embedding_model) <> ''),
  pipeline_version integer not null check (pipeline_version > 0),
  chunk_count integer not null check (chunk_count > 0),
  indexed_at timestamptz not null default now()
);

alter table public.document_indexes enable row level security;
revoke all on table public.document_indexes from public, anon, authenticated;
grant select, insert on table public.document_indexes to service_role;

commit;
