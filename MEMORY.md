# Bol-Lex AI: Architectural Decisions & System Memory

## 2026-10-22: Consolidación PMV y Resiliencia del Motor de IA

### 1. Problema Abordado
- Error `404 - model_not_found` al invocar `llama-3.3-70b-versatile` en Groq desde Streamlit Cloud debido a modelos retirados, descontinuados o no autorizados para el API Key configurado.
- Fallo latente en OCR por descontinuación de `llama-3.2-11b-vision-preview`.
- Regresión funcional por remoción de módulos forenses de Memoriales (.docx), Consultorio interactivo y Archivo documental.

### 2. Decisiones Arquitectónicas (ADR)
- **Selección Dinámica y Fallback en Cascada**:
  - `inicializar_motor_ia()` consulta `cliente.models.list()` para descubrir los modelos activos de la cuenta.
  - Ejecuta una prueba en caliente (*dry-run* con `max_tokens=2`) verificando respuesta HTTP 200 antes de asignar el modelo.
  - Prioridad: `llama-3.3-70b-versatile` -> `llama-3.1-70b-versatile` -> `llama-3.1-8b-instant` -> `mixtral-8x7b-32768` -> `gemma2-9b-it` -> primer modelo válido.
  - `invocar_groq_con_fallback()` conmuta automáticamente de modelo durante el procesamiento si se detecta `model_not_found`, `does not exist` o `404`.
- **OCR Híbrido y Defensivo**:
  - Prioridad 1: Extracción digital directa con `PdfReader`.
  - Prioridad 2: `RapidOCR` local con `pypdfium2` (sin depender de APIs de visión externas volátiles).
- **Consolidación de Módulos PMV**:
  - Pestaña 1: Dictamen y Diagnóstico Jurídico (con descarga en PDF).
  - Pestaña 2: Redactor Forense de Memoriales (con descarga en Word `.docx` y PDF).
  - Pestaña 3: Consultorio Jurídico y Análisis de Conexidad Global Intercasos.
  - Pestaña 4: Archivo Documental del Expediente Activo.
