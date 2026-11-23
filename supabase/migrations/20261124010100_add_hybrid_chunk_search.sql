begin;

create index document_chunks_content_fts_idx on public.document_chunks using gin (
  to_tsvector('pg_catalog.spanish'::regconfig, content)
);

create function public.match_document_chunks_hybrid(
  target_document_id text,
  query_text text,
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
  with consulta as (
    select websearch_to_tsquery('pg_catalog.spanish'::regconfig, query_text) as terminos
  ),
  candidatos_semanticos as (
    select c.chunk_index, c.embedding operator(extensions.<=>) query_embedding as distancia
    from public.document_chunks as c
    where c.document_id = target_document_id
    order by distancia, c.chunk_index
    limit 20
  ),
  semantica as (
    select s.chunk_index, row_number() over (order by s.distancia, s.chunk_index) as posicion
    from candidatos_semanticos as s
  ),
  candidatos_lexicos as (
    select c.chunk_index,
      ts_rank(to_tsvector('pg_catalog.spanish'::regconfig, c.content), q.terminos) as relevancia
    from public.document_chunks as c cross join consulta as q
    where c.document_id = target_document_id
      and to_tsvector('pg_catalog.spanish'::regconfig, c.content) @@ q.terminos
    order by relevancia desc, c.chunk_index
    limit 20
  ),
  lexica as (
    select l.chunk_index, row_number() over (order by l.relevancia desc, l.chunk_index) as posicion
    from candidatos_lexicos as l
  ),
  fusion as (
    select coalesce(s.chunk_index, l.chunk_index) as chunk_index,
      coalesce(1.0 / (60 + s.posicion), 0) + coalesce(1.0 / (60 + l.posicion), 0) as puntuacion,
      s.posicion as posicion_semantica
    from semantica as s full join lexica as l on l.chunk_index = s.chunk_index
  )
  select c.chunk_index, c.page_number, c.content,
    1 - (c.embedding operator(extensions.<=>) query_embedding) as similarity
  from fusion as f
  join public.document_chunks as c
    on c.document_id = target_document_id and c.chunk_index = f.chunk_index
  order by f.puntuacion desc, f.posicion_semantica nulls last, c.chunk_index
  limit greatest(1, least(coalesce(match_count, 5), 10));
$$;

revoke all on function public.match_document_chunks_hybrid(text, text, extensions.vector, integer)
  from public, anon, authenticated;
grant execute on function public.match_document_chunks_hybrid(text, text, extensions.vector, integer)
  to service_role;

commit;
