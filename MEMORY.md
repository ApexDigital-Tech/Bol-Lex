# Bol-Lex AI: Architectural Decisions & System Memory

## 2026-10-22: Reestructuración Integral Agéntica Bol-Lex 3.0 (Zero-Hallucination & Scraper TCP)

### 1. Causas de Falla Anteriores
- **Alucinación Forzada por RAG Monotemático**: El sistema anterior poseía un único fallo en su base (`SCP 0084/2017-S3`, fuero de maternidad laboral) e inyectaba obligatoriamente esa sentencia en controversias de contratos y deudas de empresas públicas (EBC/Ecotraffic), forzando a la IA a requerir certificados de embarazo en litigios comerciales.
- **Falla de Extracción Silenciosa**: PDFs escaneados retornaban cadenas vacías sin diagnóstico visible, provocando que la IA dedujera la ausencia total de documentos.
- **Monolito de Código**: Más de 700 líneas acopladas en un solo archivo `app_bufete.py`.

### 2. Nueva Arquitectura Modular Agéntica (Bol-Lex 3.0)
- **`core/llm_client.py`**: Motor de inferencia Groq con descubrimiento dinámico y fallback en cascada.
- **`core/extractor.py`**: Extractor híbrido (digital nativo + OCR local con RapidOCR) con diagnóstico de legibilidad por página. Si un documento es ilegible, emite advertencia explícita en lugar de texto vacío.
- **`core/jurisprudencia/`**:
  - `corpus_data.py`: Corpus verificado y clasificado en Civil, Contrataciones Estatales (DS 0181 / Ley 1178), Constitucional (Amparo), Laboral y Penal.
  - `tcp_scraper.py`: Motor de búsqueda y scraping para resoluciones del Tribunal Constitucional Plurinacional (Aletheia / tcpbolivia.bo).
  - `rag_engine.py`: Búsqueda semántica con **aislamiento estricto de materia** (un caso civil jamás consulta ni recibe fallos laborales).
- **`core/agents/` (Equipo Agéntico Senior)**:
  - `director.py`: Agente 1 (Triaje, calificación jurídica y vía procesal).
  - `evidence_auditor.py`: Agente 2 (Auditoría probatoria estricta, hechos 100% certificados, prohibición de inventar supuestos).
  - `specialist.py`: Agente 3 (Dictamen estratégico según materia procesal y subsunción del precedente vinculante real).
  - `forensic_writer.py`: Agente 4 (Redacción de memorial judicial boliviano en `.docx` y `.pdf`).
- **`core/bufete_orchestrator.py`**: Orquestación y trazabilidad del flujo agéntico.
- **`app_bufete.py`**: UI en Streamlit con pestaña dedicada de **Scraper & Buscador TCP**, Dictamen, Memorial .docx, Consultorio y Archivo Documental.

### 3. Resiliencia del Bucle Agéntico y Auto-Continuación (Post-Corte & Zero-Truncation)
- **Causa Raíz de 'Detención a Medio Camino'**: El motor LLM alcanzaba el límite por defecto de tokens de salida (`finish_reason == 'length'`) en documentos legales extensos (Dictamen y Memorial), cortando el análisis en las últimas secciones. Adicionalmente, auditorías de múltiples piezas consecutivas podían disparar cuotas TPM/RPM (429) sin backoff.
- **Bucle Agéntico de Continuación (`auto_continuar=True`)**: `core/llm_client.py` detecta si `finish_reason == 'length'`, preserva el contexto acumulado y encadena automáticamente hasta 3 ciclos de continuación sin repetición hasta alcanzar el final formal (`finish_reason == 'stop'`).
- **Backoff Defensivo y Gestión de Modelos**: Pausa de 2.0s ante 429 rate limit y salvaguarda de fallback entre modelos (Llama-3.3-70b, Llama-3.1-8b, Qwen, etc.).
- **Credenciales Dinámicas en UI**: Soporte de ingreso o actualización de `GROQ_API_KEY` directamente en la barra lateral si el entorno carece de secretos precargados.
### 4. Gestión Defensiva de Ventana de Contexto (Fix Error 400 'reduce the length of the messages or completion')
- **Causa Raíz**: Modelos con ventanas de contexto reducidas (8,192 tokens como Qwen o Gemma) no toleran la suma de prompts forenses acumulados (~4,500 tokens) más cuotas altas de salida (`max_tokens=4096`), superando el límite duro de la API de Groq (8,192 tokens totales).
- **Auto-Recuperación y Auto-Escalado (128k Fallback)**: `core/llm_client.py` captura activamente errores de contexto excedido y conmuta instantáneamente a modelos con 128,000 tokens de contexto (`llama-3.3-70b-versatile` o `llama-3.1-8b-instant`).
- **Transparencia en UI**: Selector de modelos en la barra lateral con insignias de capacidad (`128k - Recomendado`, `128k - Rápido`, `8k - No recomendado para expedientes`).

### 5. Presupuesto Matemático Proactivo Anti-Error 400 (Groq Free Tier Ceiling de 6,000 TPM)
- **Causa Raíz Real del Error 400**: En la capa gratuita de Groq, la organización impone un límite de **6,000 TPM** (Tokens Por Minuto) y rechaza con HTTP 400 (`reduce the length of the messages or completion`) cualquier petición individual donde `prompt_tokens + max_tokens > 6,000`. Al solicitar `max_tokens=3200` sobre prompts de ~3,500 tokens (informes de auditoría de múltiples contratos), la suma daba > 6,700 tokens, fallando incluso en Llama 3.3 70b.
- **Blindaje Proactivo (`MAX_REQUEST_TOTAL_TOKENS = 4200`)**: En lugar de esperar a que ocurra un error 400, `core/llm_client.py` ahora calcula y normaliza el presupuesto *antes* de enviar la petición:
  1. Clampa la salida a un valor óptimo (1,000 tokens en JSON, 1,800 tokens en dictamen/memorial).
  2. Ajusta proporcionalmente los fragmentos probatorios extensos para que el prompt nunca exceda 2,400 tokens (~7,200 caracteres).
  3. La suma total nunca supera 4,200 tokens, quedando matemáticamente blindada bajo el techo de 6,000 TPM de Groq.
- **Bucle de Continuación Ligero**: El bucle de auto-continuación no reenvía el texto acumulado completo (lo que inflaba el prompt a miles de tokens), sino únicamente las últimas 600 letras como anclaje sintáctico en un prompt de ~250 tokens con `max_tokens=1200`.
- **Elección Óptima de Agente/Modelo**:
  - `🌟 llama-3.3-70b-versatile`: Modelo principal recomendado (máxima calidad analítica y jurisprudencial).
  - `⚡ llama-3.1-8b-instant`: Modelo secundario recomendado (ultra rápido, latencia mínima).
