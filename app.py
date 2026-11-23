import streamlit as st
from openai import APIError

from rag import Respuesta, RespuestaModeloInvalida, id_indice, preparar_pdf, responder


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
document_id = id_indice(pdf)

if st.session_state.get("document_id") != document_id:
    if not st.button("Preparar PDF"):
        st.stop()

    try:
        with st.spinner("Preparando el índice del PDF…"):
            indice = preparar_pdf(pdf)
    except ValueError as error:
        st.error(str(error))
        st.stop()
    except Exception:
        st.error("No se pudo preparar el PDF. Revisa el archivo, Ollama y Supabase y reintenta.")
        st.stop()

    st.session_state.document_id = document_id
    st.session_state.mensajes = []
    st.session_state.indice = indice

indice = st.session_state.indice
estado = "Índice reutilizado" if indice.reutilizado else "PDF indexado"
st.caption(f"{estado} · {indice.cantidad} fragmentos")
modo_busqueda = st.radio("Búsqueda", ("Semántica", "Híbrida"), horizontal=True)

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
            respuesta = responder(document_id, pregunta, busqueda_hibrida=modo_busqueda == "Híbrida")
    except RespuestaModeloInvalida:
        st.error("Ollama devolvió una respuesta que no se pudo verificar. Intenta de nuevo.")
        st.stop()
    except APIError:
        st.error("No se pudo completar la consulta en Ollama. Revisa que esté en ejecución.")
        st.stop()
    except Exception:
        st.error("No se pudo consultar el PDF. Revisa Ollama y Supabase.")
        st.stop()

    mostrar_respuesta(respuesta)
    st.session_state.mensajes.extend([
        ("user", pregunta),
        ("assistant", respuesta),
    ])
