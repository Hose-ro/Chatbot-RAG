from hashlib import sha256
from io import BytesIO

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

def extraer_fragmentos(pdf: bytes) ->list[dict]:
    document_id = sha256(pdf).hexdigest()
    lector = PdfReader(BytesIO(pdf))
    divisor = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150, length_function=len)
    fragmentos = []
    for pagina, hoja in enumerate(lector.pages, start=1):
        texto = hoja.extract_text() or ""
        for contenido in divisor.split_text(texto):
            fragmentos.append({
                "document_id": document_id,
                "chunk_index": len(fragmentos),
                "page_number": pagina,
                "content": contenido
                
            })

    if not fragmentos:
        raise ValueError("El PDF no contiene texto seleccionable.")

    return fragmentos
