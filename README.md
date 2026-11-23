# Chatbot RAG

Consulta un PDF con texto seleccionable desde Streamlit. La app usa pypdf para extraer el texto por página y LangChain para dividirlo en fragmentos de hasta 1 000 caracteres con un solapamiento configurado de 150. Supabase guarda el texto y los vectores de 1 024 dimensiones. Al preguntar, la app recupera hasta cinco fragmentos del PDF activo por similitud coseno y cita la página con el formato `[p. N]`.

Ollama ejecuta el modelo de chat y el de embeddings en tu equipo. El SDK de OpenAI se conecta a `http://127.0.0.1:11434/v1` con el valor de relleno `ollama`.

## Configuración en Windows

Necesitas Python 3.12, Ollama y un proyecto de Supabase con la tabla `document_chunks` y la función `match_document_chunks`. En el proyecto `chatbot-rag` ya se aplicó la [migración a 1 024 dimensiones](supabase/migrations/20261123042825_ollama_embedding_1024.sql).

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

## Prueba de Aurora

1. Crea un PDF de una página con el texto «El presupuesto del proyecto Aurora es de 47 pesos». Comprueba que puedas seleccionar el texto.
2. Sube el archivo a Streamlit y pulsa **Indexar PDF**.
3. Haz estas dos preguntas y compara las respuestas con los resultados esperados.

| Pregunta | Resultado esperado |
| --- | --- |
| ¿Cuál es el presupuesto del proyecto Aurora? | `47 pesos [p. 1]` |
| ¿Quién aprobó el presupuesto? | `No hay evidencia en el PDF para responder esa pregunta.` |
