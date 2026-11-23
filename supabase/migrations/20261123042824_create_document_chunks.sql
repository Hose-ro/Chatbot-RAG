begin;

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table public.document_chunks (
  document_id text not null check (document_id ~ '^[0-9a-f]{64}$'),
  chunk_index integer not null check (chunk_index >= 0),
  page_number integer not null check (page_number > 0),
  content text not null check (btrim(content) <> ''),
  embedding extensions.vector(1536) not null,
  primary key (document_id, chunk_index)
);

alter table public.document_chunks enable row level security;
revoke all on table public.document_chunks from public, anon, authenticated;
grant select, insert, update on table public.document_chunks to service_role;

create function public.match_document_chunks(
  target_document_id text,
  query_embedding extensions.vector,
  match_count integer default 5
)
returns table (
  chunk_index integer,
  page_number integer,
  content text,
  similarity double precision
)
language sql
stable
set search_path = ''
as $$
  select
    chunks.chunk_index,
    chunks.page_number,
    chunks.content,
    1 - (chunks.embedding operator(extensions.<=>) query_embedding) as similarity
  from public.document_chunks as chunks
  where chunks.document_id = target_document_id
  order by chunks.embedding operator(extensions.<=>) query_embedding, chunks.chunk_index
  limit greatest(1, least(coalesce(match_count, 5), 10));
$$;

revoke all on function public.match_document_chunks(text, extensions.vector, integer)
  from public, anon, authenticated;
grant execute on function public.match_document_chunks(text, extensions.vector, integer)
  to service_role;

commit;
