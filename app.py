from hashlib import sha256

import streamlit as st

from documentos import extraer_fragmentos
from rag import Respuesta, indexar, responder


def mostrar_respuesta(respuesta: Respuesta) -> None:
    with st.chat_message("assistant"):
        st.text(respuesta.texto)
        if respuesta.fuente:
            with st.expander(f"Ver fuente · p. {respuesta.fuente.pagina}"):
                st.text(respuesta.fuente.contenido)

st.title("Chatbot RAG")
archivo = st.file_uploader("Sube un PDF con texto seleccionable", type="pdf")

if archivo is None:
    st.stop()

pdf = archivo.getvalue()
document_id = sha256(pdf).hexdigest()

if st.session_state.get("document_id") != document_id:
    if not st.button("Indexar PDF"):
        st.stop()

    try:
        with st.spinner("Indexando el PDF…"):
            indexar(extraer_fragmentos(pdf))
    except ValueError as error:
        st.error(str(error))
        st.stop()
    except Exception:
        st.error("No se pudo indexar el PDF. Revisa el archivo, Ollama y Supabase.")
        st.stop()

    st.session_state.document_id = document_id
    st.session_state.mensajes = []

for rol, contenido in st.session_state.mensajes:
    if rol == "assistant":
        mostrar_respuesta(contenido)
    else:
        st.chat_message(rol).text(contenido)

pregunta = st.chat_input("Pregunta sobre el PDF activo")
if pregunta and pregunta.strip():
    pregunta = pregunta.strip()
    st.chat_message("user").text(pregunta)

    try:
        with st.spinner("Buscando en el PDF…"):
            respuesta = responder(document_id, pregunta)
    except Exception:
        st.error("No se pudo consultar el PDF. Revisa Ollama y Supabase.")
        st.stop()

    mostrar_respuesta(respuesta)
    st.session_state.mensajes.extend([
        ("user", pregunta),
        ("assistant", respuesta),
    ])
