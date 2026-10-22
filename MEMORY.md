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
- **Presupuesto Proactivo de Tokens**: Ajuste dinámico de `tokens_efectivos = max(1000, min(tokens_salida, 7800 - tokens_estimados))` en modelos de 8k para garantizar que ningún llamado exceda la capacidad del modelo elegido.
- **Transparencia en UI**: Selector de modelos en la barra lateral con insignias de capacidad (`128k - Recomendado`, `128k - Rápido`, `8k - Contexto Estrecho`).
