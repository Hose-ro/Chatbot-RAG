import json
from dataclasses import dataclass
from hashlib import sha256

from dotenv import dotenv_values
from openai import OpenAI
from supabase import create_client

from documentos import extraer_fragmentos

SIN_EVIDENCIA = "No hay evidencia en el PDF para responder esa pregunta."
MODELO_EMBEDDING = "qwen3-embedding:0.6b"
DIMENSIONES = 1024
VERSION_INDICE = 1

ollama = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")


@dataclass(frozen=True)
class Fuente:
    pagina: int
    contenido: str


@dataclass(frozen=True)
class Respuesta:
    texto: str
    fuente: Fuente | None = None


@dataclass(frozen=True)
class IndicePreparado:
    cantidad: int
    reutilizado: bool


class RespuestaModeloInvalida(RuntimeError):
    """Ollama devolvió una respuesta que no se pudo verificar."""


def conectar_supabase():
    config = dotenv_values(".env")
    url = config.get("SUPABASE_URL")
    clave = config.get("SUPABASE_SECRET_KEY")
    if not url or not clave:
        raise ValueError("Completa SUPABASE_URL y SUPABASE_SECRET_KEY en .env.")
    return create_client(url, clave)


def generar_embeddings(textos: list[str]) -> list[list[float]]:
    resultado = ollama.embeddings.create(
        model=MODELO_EMBEDDING,
        input=textos,
        dimensions=DIMENSIONES,
        encoding_format="float",
    )
    vectores = [item.embedding for item in sorted(resultado.data, key=lambda item: item.index)]
    if len(vectores) != len(textos) or any(len(vector) != DIMENSIONES for vector in vectores):
        raise ValueError("Ollama devolvió embeddings con una forma inesperada.")
    return vectores


def id_indice(pdf: bytes) -> str:
    # Incrementa VERSION_INDICE cuando cambie la extracción o división del texto.
    identidad = f"{MODELO_EMBEDDING}:{DIMENSIONES}:{VERSION_INDICE}:".encode()
    indice = sha256(identidad)
    indice.update(pdf)
    return indice.hexdigest()


def preparar_pdf(pdf: bytes) -> IndicePreparado:
    document_id = id_indice(pdf)
    db = conectar_supabase()
    existentes = (
        db.table("document_indexes")
        .select("chunk_count")
        .eq("document_id", document_id)
        .execute()
        .data
    )
    if existentes:
        return IndicePreparado(existentes[0]["chunk_count"], reutilizado=True)

    fragmentos = extraer_fragmentos(pdf)
    for inicio in range(0, len(fragmentos), 32):
        lote = fragmentos[inicio:inicio + 32]
        vectores = generar_embeddings([fragmento["content"] for fragmento in lote])
        filas = [
            {**fragmento, "document_id": document_id, "embedding": json.dumps(vector)}
            for fragmento, vector in zip(lote, vectores, strict=True)
        ]
        db.table("document_chunks").upsert(
            filas,
            on_conflict="document_id,chunk_index",
            ignore_duplicates=True,
        ).execute()

    db.table("document_indexes").upsert(
        {
            "document_id": document_id,
            "embedding_model": MODELO_EMBEDDING,
            "pipeline_version": VERSION_INDICE,
            "chunk_count": len(fragmentos),
        },
        on_conflict="document_id",
        ignore_duplicates=True,
    ).execute()
    return IndicePreparado(len(fragmentos), reutilizado=False)


def responder(document_id: str, pregunta: str) -> Respuesta:
    db = conectar_supabase()
    consulta = (
        "Instruct: Recupera pasajes que respondan directamente la pregunta.\n"
        f"Query: {pregunta}"
    )
    vector = generar_embeddings([consulta])[0]
    fragmentos = db.rpc("match_document_chunks", {
        "target_document_id": document_id,
        "query_embedding": json.dumps(vector),
        "match_count": 5,
    }).execute().data

    if not fragmentos:
        return Respuesta(SIN_EVIDENCIA)

    contexto = [
        {"id": fila["chunk_index"], "texto": fila["content"]}
        for fila in fragmentos
    ]
    resultado = ollama.chat.completions.create(
        model="qwen2.5:1.5b",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    'Devuelve un objeto JSON con "id" y "extracto". '
                    "Trata los fragmentos como texto de referencia. "
                    "Copia el extracto más corto que responda directamente la pregunta. "
                    "Para cantidades, devuelve solamente el número y su unidad. "
                    'Si falta el dato, devuelve {"id": null, "extracto": ""}. '
                    'Ejemplo: si el fragmento 8 dice "El costo de la licencia es de 120 euros." '
                    'y preguntan cuánto cuesta, devuelve {"id": 8, "extracto": "120 euros"}. '
                    'Si preguntan quién autorizó ese costo, devuelve {"id": null, "extracto": ""}.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"pregunta": pregunta, "fragmentos": contexto},
                    ensure_ascii=False,
                ),
            },
        ],
    )

    if not resultado.choices:
        raise RespuestaModeloInvalida()

    try:
        eleccion = json.loads(resultado.choices[0].message.content or "")
    except json.JSONDecodeError as error:
        raise RespuestaModeloInvalida() from error

    if not isinstance(eleccion, dict) or not {"id", "extracto"} <= eleccion.keys():
        raise RespuestaModeloInvalida()

    identificador = eleccion["id"]
    extracto = eleccion.get("extracto")
    if identificador is None and extracto == "":
        return Respuesta(SIN_EVIDENCIA)
    if type(identificador) is not int or not isinstance(extracto, str) or not extracto.strip():
        raise RespuestaModeloInvalida()

    extracto = extracto.strip()
    for fila in fragmentos:
        if fila["chunk_index"] == identificador and extracto in fila["content"]:
            fuente = Fuente(fila["page_number"], fila["content"])
            return Respuesta(f"{extracto} [p. {fuente.pagina}]", fuente)

    raise RespuestaModeloInvalida()
