# Chatbot RAG

Consulta un PDF con texto seleccionable desde Streamlit. La app usa pypdf para extraer el texto por página y LangChain para dividirlo en fragmentos de hasta 1 000 caracteres con un solapamiento configurado de 150. Supabase guarda el texto y los vectores de 1 024 dimensiones. El chat recupera hasta cinco fragmentos del PDF activo. Las respuestas incluyen la cita `[p. N]` y el desplegable **Ver fuente** muestra el fragmento citado.

Ollama ejecuta el modelo de chat y el de embeddings en tu equipo. El SDK de OpenAI se conecta a `http://127.0.0.1:11434/v1` con el valor de relleno `ollama`.

## Configuración en Windows

Necesitas Python 3.12, Ollama y un proyecto de Supabase. En `chatbot-rag` ya están desplegadas las tablas y funciones que usa esta versión.

Para preparar un proyecto Supabase vacío desde el editor SQL, ejecuta estos archivos en orden:

1. [Esquema inicial con pgvector y búsqueda semántica](supabase/migrations/20261123042824_create_document_chunks.sql)
2. [Cambio a embeddings de 1 024 dimensiones](supabase/migrations/20261123042825_ollama_embedding_1024.sql)
3. [Registro de índices completados](supabase/migrations/20261124010000_track_document_indexes.sql)
4. [Búsqueda híbrida](supabase/migrations/20261124010100_add_hybrid_chunk_search.sql)

El esquema inicial reconstruye la primera etapa de la base. En instalaciones existentes aplica solo los cambios pendientes. La migración a 1 024 dimensiones requiere que `document_chunks` esté vacía y se detiene si encuentra filas.

### Ejecutar la app

1. Abre la carpeta del proyecto en VS Code y usa una terminal de PowerShell. Si ya tienes `.venv`, puedes omitir el comando que lo crea.

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Abre Ollama y descarga los modelos.

   ```powershell
   ollama pull qwen2.5:1.5b
   ollama pull qwen3-embedding:0.6b
   ```

3. Crea o completa el archivo local `.env` con la URL del proyecto y su clave secreta, disponible en **Project Settings → API Keys**. Git ignora este archivo.

   ```dotenv
   SUPABASE_URL=https://TU_PROYECTO.supabase.co
   SUPABASE_SECRET_KEY=TU_CLAVE_SECRETA
   ```

4. Con `app.py` en la carpeta del proyecto, ejecuta Streamlit y abre `http://127.0.0.1:8501`.

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
   ```

## Preparar y consultar un PDF

1. Sube un PDF y pulsa **Preparar PDF**. La primera vez se calculan los embeddings. Si ya existe un índice completo para el archivo, el modelo y la versión del procesamiento, la app muestra **Índice reutilizado**.
2. Elige **Semántica** para recuperar por similitud coseno o **Híbrida** para combinar similitud coseno y coincidencias de texto en español. Prueba la búsqueda híbrida con folios, nombres o códigos exactos.
3. Haz una pregunta sobre el PDF activo. Abre **Ver fuente** debajo de la respuesta para leer el fragmento citado. Si Ollama devuelve una salida inválida, la app indica que la respuesta no se pudo verificar.

Los PDFs procesados antes del registro de índices se indexarán una vez al prepararlos con esta versión. Los fragmentos anteriores permanecen en Supabase.

## Prueba de Aurora

1. Crea un PDF de una página con el texto «El presupuesto del proyecto Aurora es de 47 pesos». Comprueba que puedas seleccionar el texto.
2. Sube el archivo a Streamlit y pulsa **Preparar PDF**.
3. Haz estas dos preguntas y compara las respuestas con los resultados esperados.

| Pregunta | Resultado esperado |
| --- | --- |
| ¿Cuál es el presupuesto del proyecto Aurora? | `47 pesos [p. 1]` |
| ¿Quién aprobó el presupuesto? | `No hay evidencia en el PDF para responder esa pregunta.` |

Repite ambas preguntas en los dos modos de búsqueda. Añade una portada vacía al PDF y comprueba que el importe cite `[p. 2]`.

### Pruebas automatizadas

Las pruebas de Python generan PDFs seleccionables y simulan las respuestas de Ollama y Supabase. Ejecútalas desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

La [prueba SQL de búsqueda híbrida](tests/sql/hybrid_search.sql) compara el top 5 semántico con el híbrido, verifica el aislamiento entre PDFs y revierte sus datos al terminar. Ejecútala en una base de pruebas con las cuatro migraciones aplicadas.
