begin;
set local role service_role;

insert into public.document_chunks (document_id, chunk_index, page_number, content, embedding)
select repeat('a', 64), i, i + 1,
  case when i = 6 then 'El folio AZ104 fue aprobado.' else 'El presupuesto del proyecto.' end,
  (array[1, i] || array_fill(0, array[1022]))::extensions.vector
from generate_series(0, 6) as i;

insert into public.document_chunks (document_id, chunk_index, page_number, content, embedding)
values (repeat('b', 64), 99, 99, 'AZ104',
  (array[1, 0] || array_fill(0, array[1022]))::extensions.vector);

do $$
declare
  consulta extensions.vector := (array[1, 0] || array_fill(0, array[1022]))::extensions.vector;
  semantica integer[];
  hibrida integer[];
  sin_palabras integer[];
begin
  select array_agg(m.chunk_index order by m.ordinality) into semantica
  from public.match_document_chunks(repeat('a', 64), consulta, 5) with ordinality as m;

  select array_agg(m.chunk_index order by m.ordinality) into hibrida
  from public.match_document_chunks_hybrid(repeat('a', 64), 'AZ104', consulta, 5)
    with ordinality as m;

  select array_agg(m.chunk_index order by m.ordinality) into sin_palabras
  from public.match_document_chunks_hybrid(repeat('a', 64), 'zzysinmatch', consulta, 5)
    with ordinality as m;

  if semantica is distinct from array[0, 1, 2, 3, 4]
    or hibrida is distinct from array[6, 0, 1, 2, 3]
    or sin_palabras is distinct from semantica then
    raise exception 'Ranking inesperado: %, %, %', semantica, hibrida, sin_palabras;
  end if;
end;
$$;

rollback;
