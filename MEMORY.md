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
