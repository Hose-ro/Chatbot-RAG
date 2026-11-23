begin;

lock table public.document_chunks in access exclusive mode;

do $$
begin
  if exists (select 1 from public.document_chunks) then
    raise exception 'document_chunks contiene filas. Genera los embeddings de 1024 dimensiones a partir de su contenido antes de migrar.';
  end if;
end;
$$;

alter table public.document_chunks
  alter column embedding type extensions.vector(1024)
  using embedding::extensions.vector(1024);

commit;
