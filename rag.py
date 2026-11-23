import json
from dataclasses import dataclass

from dotenv import dotenv_values
from openai import OpenAI
from supabase import create_client

SIN_EVIDENCIA = "No hay evidencia en el PDF para responder esa pregunta."

ollama = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")


@dataclass(frozen=True)
class Fuente:
    pagina: int
    contenido: str


@dataclass(frozen=True)
class Respuesta:
    texto: str
    fuente: Fuente | None = None


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
        model="qwen3-embedding:0.6b",
        input=textos,
        dimensions=1024,
        encoding_format="float",
    )
    vectores = [item.embedding for item in sorted(resultado.data, key=lambda item: item.index)]
    if len(vectores) != len(textos) or any(len(vector) != 1024 for vector in vectores):
        raise ValueError("Ollama devolvió embeddings con una forma inesperada.")
    return vectores


def indexar(fragmentos: list[dict]) -> None:
    db = conectar_supabase()
    for inicio in range(0, len(fragmentos), 32):
        lote = fragmentos[inicio:inicio + 32]
        vectores = generar_embeddings([fragmento["content"] for fragmento in lote])
        filas = [
            {**fragmento, "embedding": json.dumps(vector)}
            for fragmento, vector in zip(lote, vectores, strict=True)
        ]
        db.table("document_chunks").upsert(
            filas,
            on_conflict="document_id,chunk_index",
        ).execute()


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
                    "Si preguntan por una cantidad, copia la cantidad y su unidad. "
                    'Si falta el dato, devuelve {"id": null, "extracto": ""}. '
                    "Una cifra de presupuesto por sí sola no identifica a quien lo aprobó."
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
