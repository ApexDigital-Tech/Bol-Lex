import os
import io
import json
import shutil
from datetime import datetime
import streamlit as st

from core.bufete_orchestrator import OrquestadorBufete
from core.extractor import ExtractorDocumental
from core.jurisprudencia import ScraperTCP
import gdown

st.set_page_config(page_title="Bol-Lex AI - Bufete Digital Especializado", page_icon="⚖️", layout="wide")

# =====================================================================
# INICIALIZACIÓN DEL ORQUESTADOR MULTI-AGENTE
# =====================================================================
@st.cache_resource
def obtener_orquestador() -> OrquestadorBufete:
    return OrquestadorBufete()

orquestador = obtener_orquestador()
scraper_tcp = ScraperTCP()

# =====================================================================
# ESTADO DE SESIÓN
# =====================================================================
VARIABLES_SESION = {
    "dictamen_actual": "",
    "memorial_actual": "",
    "carpeta_actual": "",
    "codigo_caso_actual": "",
    "titulo_caso_actual": "",
    "materia_detectada": "Civil",
    "historial_consultas": [],
    "evidencia_acumulada": "",
    "logs_ejecucion": [],
    "fichas_auditadas": [],
    "precedente_usado": None
}

for k, v in VARIABLES_SESION.items():
    if k not in st.session_state:
        st.session_state[k] = v

def reiniciar_caso():
    for k, v in VARIABLES_SESION.items():
        st.session_state[k] = v
    st.rerun()

def obtener_metadatos_caso(ruta_caso: str) -> dict:
    ruta_meta = os.path.join(ruta_caso, "meta.json")
    if os.path.exists(ruta_meta):
        try:
            with open(ruta_meta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"titulo": "", "codigo": os.path.basename(ruta_caso), "fecha": "", "materia": "Civil"}

def guardar_metadatos_caso(ruta_caso: str, titulo: str, codigo: str, materia: str):
    ruta_meta = os.path.join(ruta_caso, "meta.json")
    datos = {
        "titulo": titulo.strip(),
        "codigo": codigo,
        "materia": materia,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def listar_expedientes_locales() -> dict:
    ruta_base = "Expedientes"
    if not os.path.exists(ruta_base):
        os.makedirs(ruta_base, exist_ok=True)
        return {}
    carpetas = [d for d in os.listdir(ruta_base) if os.path.isdir(os.path.join(ruta_base, d))]
    carpetas.sort(reverse=True)
    mapa = {}
    for c in carpetas:
        ruta_c = os.path.join(ruta_base, c)
        meta = obtener_metadatos_caso(ruta_c)
        nom = meta.get("titulo", "").strip()
        etiq = f"{nom} — [{c}]" if (nom and nom != c) else c
        mapa[etiq] = c
    return mapa

def cargar_expediente(codigo_caso: str):
    ruta_caso = os.path.join("Expedientes", codigo_caso)
    if not os.path.exists(ruta_caso):
        return
    meta = obtener_metadatos_caso(ruta_caso)
    st.session_state.codigo_caso_actual = codigo_caso
    st.session_state.carpeta_actual = ruta_caso
    st.session_state.titulo_caso_actual = meta.get("titulo", "")
    st.session_state.materia_detectada = meta.get("materia", "Civil")

    ruta_dict = os.path.join(ruta_caso, f"Dictamen_{codigo_caso}.md")
    st.session_state.dictamen_actual = open(ruta_dict, "r", encoding="utf-8").read() if os.path.exists(ruta_dict) else ""

    ruta_mem = os.path.join(ruta_caso, f"Memorial_{codigo_caso}.docx")
    if os.path.exists(ruta_mem):
        try:
            from docx import Document
            doc = Document(ruta_mem)
            st.session_state.memorial_actual = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception:
            st.session_state.memorial_actual = ""
    else:
        st.session_state.memorial_actual = ""

    st.rerun()

# =====================================================================
# BARRA LATERAL (GESTIÓN Y CONTROL AGÉNTICO)
# =====================================================================
with st.sidebar:
    st.title("⚖️ Bol-Lex AI")
    st.caption("Plataforma Agéntica Especializada de Litigio en Bolivia")
    
    if not orquestador.motor_llm.api_key:
        api_in = st.text_input("🔑 Ingrese Groq API Key:", type="password", placeholder="gsk_...")
        if api_in:
            orquestador.motor_llm.actualizar_api_key(api_in)
            st.rerun()
    else:
        st.success(f"🤖 IA Activa: `{orquestador.motor_llm.modelo_activo}`")
        # Selector de modelos
        modelos_opt = orquestador.motor_llm.modelos_disponibles
        idx_actual = modelos_opt.index(orquestador.motor_llm.modelo_activo) if orquestador.motor_llm.modelo_activo in modelos_opt else 0

        def formatear_modelo(m: str) -> str:
            if "3.3" in m:
                return f"🌟 {m} (Recomendado - 128k Máxima Calidad)"
            if "3.1-8b" in m:
                return f"⚡ {m} (Ultra Rápido - 128k)"
            if "3.1-70b" in m:
                return f"💎 {m} (Avanzado - 128k)"
            if "mixtral" in m:
                return f"🚀 {m} (32k)"
            if any(k in m for k in ["8192", "gemma", "qwen"]):
                return f"⚠️ {m} (8k - No recomendado para expedientes)"
            return m

        mod_elegido = st.selectbox("Cambiar Modelo Groq:", options=modelos_opt, index=idx_actual, format_func=formatear_modelo)
        if mod_elegido != orquestador.motor_llm.modelo_activo:
            orquestador.motor_llm.cambiar_modelo(mod_elegido)
            st.rerun()

    st.markdown("---")
    st.subheader("⚡ Gestión del Caso")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Guardar Caso", use_container_width=True):
            if st.session_state.carpeta_actual and os.path.exists(st.session_state.carpeta_actual):
                guardar_metadatos_caso(
                    st.session_state.carpeta_actual,
                    st.session_state.titulo_caso_actual,
                    st.session_state.codigo_caso_actual,
                    st.session_state.materia_detectada
                )
                st.toast("✅ Guardado con éxito.")
    with col2:
        if st.button("🔄 Nuevo Caso", use_container_width=True):
            reiniciar_caso()

    mapa_exp = listar_expedientes_locales()
    st.markdown("##### 📂 Historial de Expedientes")
    opciones_exp = ["-- Seleccionar caso --"] + list(mapa_exp.keys())
    idx_def = 0
    for i, op in enumerate(opciones_exp):
        if op != "-- Seleccionar caso --" and mapa_exp[op] == st.session_state.codigo_caso_actual:
            idx_def = i
            break
            
    sel_exp = st.selectbox("Cargar expediente previo:", options=opciones_exp, index=idx_def)
    if sel_exp != "-- Seleccionar caso --":
        cod = mapa_exp[sel_exp]
        if cod != st.session_state.codigo_caso_actual:
            if st.button("📥 Abrir este Expediente", use_container_width=True):
                cargar_expediente(cod)

    st.markdown("---")
    st.subheader("📁 Archivos y Pruebas del Caso")
    archivos_adjuntos = st.file_uploader(
        "Subir Contratos, Cartas, Actas (PDF, DOCX, TXT, ZIP):",
        type=["pdf", "docx", "txt", "zip"],
        accept_multiple_files=True
    )
    
    url_drive = st.text_input("🔗 O pegar enlace de Google Drive:")
    if url_drive and st.button("📥 Importar Drive", use_container_width=True):
        cod_caso = st.session_state.codigo_caso_actual or f"BOLLEX-{datetime.now().strftime('%Y%m%d-%H%M')}"
        ruta_dest = os.path.join("Expedientes", cod_caso)
        os.makedirs(ruta_dest, exist_ok=True)
        st.session_state.carpeta_actual = ruta_dest
        st.session_state.codigo_caso_actual = cod_caso
        with st.spinner("Descargando desde Google Drive..."):
            try:
                if "folders" in url_drive:
                    gdown.download_folder(url=url_drive, output=ruta_dest, quiet=False, use_cookies=False)
                else:
                    sal = gdown.download(url=url_drive, output=ruta_dest + os.sep, quiet=False, fuzzy=True)
                    if sal and sal.endswith(".zip"):
                        ExtractorDocumental.descomprimir_zip(sal, ruta_dest)
                        try:
                            os.remove(sal)
                        except Exception:
                            pass
                st.toast("✅ Archivos de Drive importados.")
                st.rerun()
            except Exception as e:
                st.error(f"Error descargando Drive: {e}")

    if st.session_state.carpeta_actual and os.path.exists(st.session_state.carpeta_actual):
        st.markdown(f"**Expediente Activo:** `{st.session_state.codigo_caso_actual}`")
        docs_en_disco = [f for f in os.listdir(st.session_state.carpeta_actual) if not f.endswith((".cache.txt", ".ficha_auditada.json", "meta.json"))]
        for f in docs_en_disco:
            st.caption(f"• {f}")

# =====================================================================
# PESTAÑAS PRINCIPALES DEL SISTEMA AGÉNTICO
# =====================================================================
st.title("⚖️ Bol-Lex AI: Plataforma Agéntica Especializada")
st.markdown("##### Litigio Estratégico, Auditoría Documental y Jurisprudencia Constitucional de Bolivia")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 Dictamen y Diagnóstico", 
    "📝 Redactor Forense (.docx)", 
    "🔎 Scraper & Buscador TCP", 
    "💬 Consultorio Litigante",
    "🗄️ Archivo Documental"
])

# ---------------------------------------------------------------------
# PESTAÑA 1: DICTAMEN Y DIAGNÓSTICO JURÍDICO
# ---------------------------------------------------------------------
with tab1:
    st.subheader("📋 Dictamen y Diagnóstico Jurídico Estratégico")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        tit_in = st.text_input(
            "🏷️ Título / Identificador del Caso:",
            value=st.session_state.titulo_caso_actual,
            placeholder="Ej: Caso Deuda EBC a Ecotraffic (Contrato Obras)"
        )
        if tit_in != st.session_state.titulo_caso_actual:
            st.session_state.titulo_caso_actual = tit_in
    with col_b:
        materia_in = st.selectbox(
            "⚖️ Materia Procesal:",
            options=["Civil", "Contrataciones Estatales", "Constitucional", "Laboral", "Penal", "Administrativo"],
            index=["Civil", "Contrataciones Estatales", "Constitucional", "Laboral", "Penal", "Administrativo"].index(st.session_state.materia_detectada) if st.session_state.materia_detectada in ["Civil", "Contrataciones Estatales", "Constitucional", "Laboral", "Penal", "Administrativo"] else 0
        )
        st.session_state.materia_detectada = materia_in

    instrucciones = st.text_area(
        "✍️ Instrucciones para el equipo de agentes especialistas:",
        value="Revisa minuciosamente los contratos y cartas adjuntos, audita la exigibilidad del saldo pendiente, determina la vía idónea (ejecutiva o amparo) y establece el plan de litigio.",
        height=90
    )

    if st.button("🚀 Iniciar Análisis con Equipo Agéntico Especializado", type="primary"):
        cod_caso = st.session_state.codigo_caso_actual or f"BOLLEX-{datetime.now().strftime('%Y%m%d-%H%M')}"
        ruta_caso = os.path.join("Expedientes", cod_caso)
        os.makedirs(ruta_caso, exist_ok=True)
        st.session_state.carpeta_actual = ruta_caso
        st.session_state.codigo_caso_actual = cod_caso

        guardar_metadatos_caso(
            ruta_caso,
            st.session_state.titulo_caso_actual or cod_caso,
            cod_caso,
            st.session_state.materia_detectada
        )

        # Guardar archivos subidos en el expediente
        if archivos_adjuntos:
            for arch in archivos_adjuntos:
                if arch.name.lower().endswith(".zip"):
                    ExtractorDocumental.descomprimir_zip(arch, ruta_caso)
                else:
                    with open(os.path.join(ruta_caso, arch.name), "wb") as f:
                        f.write(arch.getbuffer())

        with st.status("Ejecutando Pipeline Agéntico Especializado (Zero-Hallucination)...", expanded=True) as estado:
            try:
                res = orquestador.ejecutar_flujo_completo(
                    titulo_caso=st.session_state.titulo_caso_actual or cod_caso,
                    instrucciones_caso=instrucciones,
                    carpeta_caso=ruta_caso,
                    materia_preferida=st.session_state.materia_detectada
                )

                st.session_state.dictamen_actual = res["dictamen"]
                st.session_state.logs_ejecucion = res["logs"]
                st.session_state.fichas_auditadas = res["fichas"]
                st.session_state.precedente_usado = res["precedente_tcp"]
                st.session_state.evidencia_acumulada = res["evidencias_auditadas"]

                estado.update(label="✅ Análisis Agéntico Concluido Exitosamente", state="complete", expanded=False)
                st.rerun()
            except Exception as e:
                estado.update(label=f"❌ Error en la ejecución agéntica: {e}", state="error")
                st.error(f"Detalle técnico del error: {e}")

    # Mostrar logs de la última ejecución si existen
    if st.session_state.logs_ejecucion:
        with st.expander("🔍 Trazabilidad del Proceso Agéntico (Logs de Auditoría)"):
            for l in st.session_state.logs_ejecucion:
                st.text(l)

    # Mostrar el Dictamen generado
    if st.session_state.dictamen_actual:
        st.divider()
        col_d1, col_d2 = st.columns([3, 1])
        with col_d1:
            st.subheader(f"📄 Dictamen Jurídico: {st.session_state.titulo_caso_actual or st.session_state.codigo_caso_actual}")
            if st.session_state.precedente_usado:
                prec = st.session_state.precedente_usado
                st.info(f"🏛️ **Precedente TCP Vinculante Aplicado:** `{prec.get('scp_numero', 'S/N')}` ({prec.get('sala', '')}) — Materia: **{prec.get('materia', '')}**\n\n*Ratio:* {prec.get('ratio_decidendi', '')[:200]}...")
        with col_d2:
            ruta_pdf = os.path.join(st.session_state.carpeta_actual, f"Dictamen_{st.session_state.codigo_caso_actual}.pdf")
            if os.path.exists(ruta_pdf):
                with open(ruta_pdf, "rb") as fp:
                    st.download_button(
                        "📥 Descargar Dictamen en PDF", 
                        fp, 
                        file_name=f"Dictamen_{st.session_state.codigo_caso_actual}.pdf", 
                        mime="application/pdf", 
                        use_container_width=True
                    )
        st.markdown(st.session_state.dictamen_actual)

# ---------------------------------------------------------------------
# PESTAÑA 2: REDACTOR FORENSE DE MEMORIALES
# ---------------------------------------------------------------------
with tab2:
    st.subheader("📝 Redactor Forense de Memoriales Judiciales (Word .docx y PDF)")
    
    col_m1, col_m2 = st.columns([2, 1])
    with col_m1:
        abogado_in = st.text_input("Abogado patrocinante:", value="Dr. Rolando Gutierrez - M.C.A. 45892")
    with col_m2:
        suma_in = st.text_input("Suma / Tipo de Memorial:", value="Demanda Ejecutiva de Cobro de Suma Líquida y Exigible")

    notas_memorial = st.text_area("Instrucciones específicas o petitorio cautelar:", value="Solicitar embargo preventivo de cuentas bancarias en ASFI sobre los fondos de la entidad deudora.")

    if st.button("⚖️ Redactar Memorial Oficial en Formato Forense", type="primary"):
        if not st.session_state.carpeta_actual or not os.path.exists(st.session_state.carpeta_actual):
            st.warning("Primero debes cargar o procesar un expediente en la pestaña de Dictamen.")
        else:
            with st.spinner("El Agente Redactor Forense está estructurando el memorial oficial..."):
                try:
                    mem_txt, r_docx, r_pdf = orquestador.generar_memorial(
                        titulo_caso=st.session_state.titulo_caso_actual or st.session_state.codigo_caso_actual,
                        materia=st.session_state.materia_detectada,
                        suma=suma_in,
                        abogado=abogado_in,
                        carpeta_caso=st.session_state.carpeta_actual,
                        instrucciones_extra=notas_memorial
                    )
                    st.session_state.memorial_actual = mem_txt
                    st.success("✅ Memorial judicial redactado y compilado en .docx y .pdf.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error redactando memorial: {e}")

    if st.session_state.memorial_actual:
        st.divider()
        col_dw1, col_dw2, col_dw3 = st.columns([2, 1, 1])
        with col_dw1:
            st.subheader("📄 Memorial Judicial Formulado")
        with col_dw2:
            r_docx = os.path.join(st.session_state.carpeta_actual, f"Memorial_{st.session_state.codigo_caso_actual}.docx")
            if os.path.exists(r_docx):
                with open(r_docx, "rb") as f_d:
                    st.download_button(
                        label="📥 Descargar Word (.docx)",
                        data=f_d,
                        file_name=f"Memorial_{st.session_state.codigo_caso_actual}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
        with col_dw3:
            r_pdf = os.path.join(st.session_state.carpeta_actual, f"Memorial_{st.session_state.codigo_caso_actual}.pdf")
            if os.path.exists(r_pdf):
                with open(r_pdf, "rb") as f_p:
                    st.download_button(
                        label="📥 Descargar PDF",
                        data=f_p,
                        file_name=f"Memorial_{st.session_state.codigo_caso_actual}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        st.markdown(st.session_state.memorial_actual)

# ---------------------------------------------------------------------
# PESTAÑA 3: SCRAPER & BUSCADOR JURISPRUDENCIAL DEL TCP
# ---------------------------------------------------------------------
with tab3:
    st.subheader("🔎 Scraper & Buscador Jurisprudencial del TCP (Bolivia)")
    st.caption("Herramienta agéntica para la exploración y extracción de sentencias constitucionales en todas las materias.")

    col_s1, col_s2, col_s3 = st.columns([3, 2, 1])
    with col_s1:
        query_tcp = st.text_input("Palabras clave, concepto o término a buscar:", placeholder="Ej: retención indebida planillas ebc contrataciones estatales")
    with col_s2:
        materia_tcp = st.selectbox(
            "Filtrar por Materia:",
            options=["Todas", "Civil", "Contrataciones Estatales", "Constitucional", "Laboral", "Penal"],
            index=0
        )
    with col_s3:
        st.write("")
        st.write("")
        buscar_btn = st.button("🔍 Buscar Fallos", use_container_width=True)

    if buscar_btn or query_tcp:
        with st.spinner("Consultando repositorio jurisprudencial y conectando con el TCP..."):
            mat_filtro = "" if materia_tcp == "Todas" else materia_tcp
            resultados_tcp = scraper_tcp.buscar_en_linea(query_tcp, materia=mat_filtro, limite=6)

            if resultados_tcp:
                st.success(f"Se encontraron **{len(resultados_tcp)}** precedentes jurisprudenciales vinculantes:")
                for r in resultados_tcp:
                    with st.expander(f"🏛️ {r.get('scp_numero', 'SCP S/N')} — {r.get('tema', 'Sin título')} [{r.get('materia', 'General')}]", expanded=True):
                        col_r1, col_r2 = st.columns([3, 1])
                        with col_r1:
                            st.markdown(f"**Sala / Tribunal:** {r.get('sala', 'Sala Constitucional')} | **Materia:** `{r.get('materia', '')}`")
                            st.markdown(f"**Ratio Decidendi:**\n\n> {r.get('ratio_decidendi', '')}")
                        with col_r2:
                            normas = r.get("normas_clave", [])
                            if normas:
                                st.markdown("**Normas Aplicadas:**")
                                for n in normas:
                                    st.caption(f"• {n}")
                            desc = r.get("descriptores", [])
                            if desc:
                                st.markdown(f"**Descriptores:** `{', '.join(desc[:4])}`")
            else:
                st.info("No se encontraron fallos para los términos ingresados. Prueba con otros descriptores (ej: 'deuda', 'contrato', 'amparo', 'debido proceso').")

# ---------------------------------------------------------------------
# PESTAÑA 4: CONSULTORIO LITIGANTE (CHAT INTERACTIVO)
# ---------------------------------------------------------------------
with tab4:
    st.subheader("💬 Consultorio Jurídico Interactivo")
    st.caption("Interroga directamente al equipo agéntico sobre los antecedentes o la estrategia procesal del caso activo.")

    for preg, resp in st.session_state.historial_consultas:
        with st.chat_message("user"):
            st.write(preg)
        with st.chat_message("assistant"):
            st.markdown(resp)

    consulta = st.chat_input("Escribe una consulta jurídica sobre este expediente...")
    if consulta:
        with st.chat_message("user"):
            st.write(consulta)

        prompt_chat = f"""
Actúas como Consultor Jurídico Litigante Senior en Bolivia.
Dictamen emitido para este caso:
{st.session_state.dictamen_actual[:2500]}

Evidencias documentadas probadas:
{st.session_state.evidencia_acumulada[:5000]}

Pregunta del abogado:
{consulta}

REGLA: Responde con rigor procesal boliviano (artículos de leyes, excepciones, plazos). No inventes hechos no respaldados en las evidencias.
"""
        with st.spinner("Consultando con el equipo de especialistas..."):
            try:
                resp_llm = orquestador.motor_llm.invocar(
                    mensajes=[{"role": "user", "content": prompt_chat}],
                    temperatura=0.1
                )
                with st.chat_message("assistant"):
                    st.markdown(resp_llm)
                st.session_state.historial_consultas.append((consulta, resp_llm))
            except Exception as e:
                st.error(f"Error en la consulta: {e}")

# ---------------------------------------------------------------------
# PESTAÑA 5: ARCHIVO DOCUMENTAL & AUDITORÍA FORENSE
# ---------------------------------------------------------------------
with tab5:
    st.subheader("🗄️ Archivo Documental y Certificación de Evidencias")
    
    if not st.session_state.carpeta_actual or not os.path.exists(st.session_state.carpeta_actual):
        st.info("No hay un expediente activo cargado.")
    else:
        col_piezas1, col_piezas2 = st.columns(2)
        
        with col_piezas1:
            st.markdown("#### 📑 Documentos Oficiales Generados")
            archivos_exp = os.listdir(st.session_state.carpeta_actual)
            elaborados = [f for f in archivos_exp if f.startswith(("Dictamen_", "Memorial_"))]
            if elaborados:
                for el in elaborados:
                    r_el = os.path.join(st.session_state.carpeta_actual, el)
                    with open(r_el, "rb") as fp_el:
                        st.download_button(f"⬇️ Descargar {el}", fp_el, file_name=el, key=f"dw_el_{el}")
            else:
                st.caption("Aún no se han redactado memoriales o dictámenes para este caso.")

        with col_piezas2:
            st.markdown("#### 📎 Piezas Probatorias en Expediente")
            pruebas = [f for f in archivos_exp if not f.startswith(("Dictamen_", "Memorial_")) and not f.endswith((".cache.txt", ".ficha_auditada.json", "meta.json"))]
            if pruebas:
                for pr in pruebas:
                    r_pr = os.path.join(st.session_state.carpeta_actual, pr)
                    with open(r_pr, "rb") as fp_pr:
                        st.download_button(f"📎 Descargar {pr}", fp_pr, file_name=pr, key=f"dw_pr_{pr}")
            else:
                st.caption("No hay documentos adjuntos subidos.")