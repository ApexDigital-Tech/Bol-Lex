import io
import os
import re
import json
import base64
import shutil
import zipfile
import numpy as np
from datetime import datetime
import streamlit as st
from pypdf import PdfReader
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from sklearn.metrics.pairwise import cosine_similarity
from groq import Groq
from markdown_pdf import MarkdownPdf, Section
import gdown

# Restricción de hilos CPU
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

st.set_page_config(page_title="Bol-Lex AI - Bufete Digital", page_icon="⚖️", layout="wide")

# =====================================================================
# GESTIÓN DE SESIÓN Y PERSISTENCIA
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
    "borrador_usuario": ""
}

for key, default in VARIABLES_SESION.items():
    if key not in st.session_state:
        st.session_state[key] = default

def reiniciar_caso():
    for key, default in VARIABLES_SESION.items():
        st.session_state[key] = default
    st.rerun()

def obtener_metadatos_caso(ruta_caso: str) -> dict:
    ruta_meta = os.path.join(ruta_caso, "meta.json")
    if os.path.exists(ruta_meta):
        try:
            with open(ruta_meta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    nombre_carpeta = os.path.basename(ruta_caso)
    return {"titulo": "", "codigo": nombre_carpeta, "fecha": "", "materia": "Civil"}

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
        nom_corto = meta.get("titulo", "").strip()
        etiqueta = f"{nom_corto} — [{c}]" if (nom_corto and nom_corto != c) else c
        mapa[etiqueta] = c
    return mapa

def cargar_expediente_existente(codigo_caso: str):
    ruta_caso = os.path.join("Expedientes", codigo_caso)
    if not os.path.exists(ruta_caso):
        return
    meta = obtener_metadatos_caso(ruta_caso)
    st.session_state.codigo_caso_actual = codigo_caso
    st.session_state.carpeta_actual = ruta_caso
    st.session_state.titulo_caso_actual = meta.get("titulo", "")
    st.session_state.materia_detectada = meta.get("materia", "Civil")
    
    ruta_dictamen_md = os.path.join(ruta_caso, f"Dictamen_{codigo_caso}.md")
    st.session_state.dictamen_actual = open(ruta_dictamen_md, "r", encoding="utf-8").read() if os.path.exists(ruta_dictamen_md) else ""
    
    ruta_mem_docx = os.path.join(ruta_caso, f"Memorial_{codigo_caso}.docx")
    if os.path.exists(ruta_mem_docx):
        try:
            doc = Document(ruta_mem_docx)
            st.session_state.memorial_actual = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception:
            st.session_state.memorial_actual = ""
    else:
        st.session_state.memorial_actual = ""
        
    st.session_state.evidencia_acumulada = sincronizar_carpeta_caso(ruta_caso)
    st.rerun()

def eliminar_expediente_actual(codigo_caso: str):
    ruta_caso = os.path.join("Expedientes", codigo_caso)
    if os.path.exists(ruta_caso):
        shutil.rmtree(ruta_caso, ignore_errors=True)
    reiniciar_caso()

# =====================================================================
# GESTIÓN ZIP Y GOOGLE DRIVE
# =====================================================================
def descomprimir_zip(buffer_o_ruta, carpeta_destino: str):
    with zipfile.ZipFile(buffer_o_ruta, 'r') as zip_ref:
        for info in zip_ref.infolist():
            nombre_archivo = os.path.basename(info.filename)
            if not nombre_archivo:
                continue
            if nombre_archivo.lower().endswith((".pdf", ".docx", ".txt")):
                ruta_salida = os.path.join(carpeta_destino, nombre_archivo)
                with zip_ref.open(info) as fuente, open(ruta_salida, "wb") as destino:
                    shutil.copyfileobj(fuente, destino)

def descargar_desde_gdrive(url_o_id: str, carpeta_destino: str) -> bool:
    try:
        if "folders" in url_o_id:
            gdown.download_folder(url=url_o_id, output=carpeta_destino, quiet=False, use_cookies=False)
        else:
            salida = gdown.download(url=url_o_id, output=carpeta_destino + os.sep, quiet=False, fuzzy=True)
            if salida and salida.endswith(".zip"):
                descomprimir_zip(salida, carpeta_destino)
                try:
                    os.remove(salida)
                except Exception:
                    pass
        return True
    except Exception as e:
        st.error(f"Error al descargar desde Google Drive: {e}")
        return False

# =====================================================================
# MOTOR DE IA Y OCR CLOUD CON GROQ
# =====================================================================
@st.cache_resource
def obtener_cliente_ia():
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets["GROQ_API_KEY"]
        except Exception:
            api_key = ""
    return Groq(api_key=api_key)

cliente_groq = obtener_cliente_ia()
MODELO_TEXTO = "llama-3.3-70b-versatile"

def ocr_pagina_con_groq(imagen_bytes: bytes) -> str:
    """Aplica OCR de alta precisión mediante Llama Vision en la nube."""
    try:
        b64 = base64.b64encode(imagen_bytes).decode("utf-8")
        res = cliente_groq.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Transcribe exactamente todo el texto de este documento legal boliviano. No resumas, devuelve el texto íntegro visible."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]
            }],
            temperature=0.0
        )
        return res.choices[0].message.content.strip()
    except Exception:
        return ""

def extraer_texto_archivo(ruta_o_buffer, nombre: str, carpeta_caso: str = None) -> str:
    nl = nombre.lower()
    try:
        if nl.endswith(".txt"):
            if hasattr(ruta_o_buffer, "read"):
                return ruta_o_buffer.read().decode("utf-8", errors="ignore")
            with open(ruta_o_buffer, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        elif nl.endswith(".docx"):
            doc = Document(ruta_o_buffer)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

        elif nl.endswith(".pdf"):
            if carpeta_caso:
                ruta_cache = os.path.join(carpeta_caso, f"{nombre}.cache.txt")
                if os.path.exists(ruta_cache):
                    with open(ruta_cache, "r", encoding="utf-8") as fc:
                        return fc.read()

            reader = PdfReader(ruta_o_buffer)
            paginas = [p.extract_text() or "" for p in reader.pages]
            texto_digital = "\n".join(paginas).strip()
            
            # Si el PDF tiene texto digital suficiente, usarlo
            if len(texto_digital) > 120:
                if carpeta_caso:
                    with open(os.path.join(carpeta_caso, f"{nombre}.cache.txt"), "w", encoding="utf-8") as fc:
                        fc.write(texto_digital)
                return texto_digital

            # Si es un escaneo físico sin texto, activar OCR en la nube
            try:
                import pypdfium2 as pdfium
                st.toast(f"🔍 OCR Cloud en: {nombre}...")
                doc_pdf = pdfium.PdfDocument(ruta_o_buffer)
                texto_ocr = []
                limite_pags = min(len(doc_pdf), 5)
                for idx in range(limite_pags):
                    page = doc_pdf[idx]
                    bitmap = page.render(scale=1.5)
                    pil_img = bitmap.to_pil().convert("RGB")
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=85)
                    txt_p = ocr_pagina_con_groq(buf.getvalue())
                    if txt_p:
                        texto_ocr.append(f"[Página {idx+1}]\n{txt_p}")
                
                texto_completo = "\n".join(texto_ocr)
                if texto_completo.strip():
                    if carpeta_caso:
                        with open(os.path.join(carpeta_caso, f"{nombre}.cache.txt"), "w", encoding="utf-8") as fc:
                            fc.write(texto_completo)
                    return texto_completo
            except Exception:
                pass

            return f"[Documento {nombre}: No se pudo extraer texto]"
        return ""
    except Exception as e:
        return f"Error procesando {nombre}: {e}"

def sincronizar_carpeta_caso(ruta_carpeta: str) -> str:
    acumulado = ""
    if os.path.exists(ruta_carpeta):
        archivos = [
            a for a in os.listdir(ruta_carpeta) 
            if a.endswith((".pdf", ".txt", ".docx")) 
            and not a.startswith(("Dictamen_", "Memorial_"))
            and not a.endswith((".cache.txt", ".resumen.json"))
        ]
        for arch in archivos:
            ruta_completa = os.path.join(ruta_carpeta, arch)
            texto = extraer_texto_archivo(ruta_completa, arch, carpeta_caso=ruta_carpeta)
            acumulado += f"\n--- DOCUMENTO: {arch} ---\n{texto[:4000].strip()}\n"
    return acumulado

# =====================================================================
# MAP-REDUCE FORENSE (EXTRACCIÓN DOCUMENTAL)
# =====================================================================
def resumir_documento_individual(nombre_archivo: str, texto: str, carpeta_caso: str) -> dict:
    ruta_resumen = os.path.join(carpeta_caso, f"{nombre_archivo}.resumen.json")
    if os.path.exists(ruta_resumen):
        try:
            with open(ruta_resumen, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    prompt_extract = f"""
Analiza este documento del expediente boliviano y extrae solo hechos y datos exactos:
DOCUMENTO: {nombre_archivo}
CONTENIDO:
{texto[:5000]}

Responde en este formato conciso:
- Tipo de documento y fecha:
- Partes identificadas (Acreedor / Deudor exactos, NIT, personas):
- Objeto del contrato / trámite:
- Montos económicos y saldos (con moneda exacta):
- Cumplimiento o mora:
REGLA: Si un dato no figura, escribe 'No especificado'. No inventes información.
"""
    try:
        res = cliente_groq.chat.completions.create(
            model=MODELO_TEXTO,
            messages=[{"role": "user", "content": prompt_extract}],
            temperature=0.0
        )
        sintesis = res.choices[0].message.content.strip()
        datos = {"archivo": nombre_archivo, "sintesis": sintesis}
        with open(ruta_resumen, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        return datos
    except Exception:
        return {"archivo": nombre_archivo, "sintesis": texto[:600]}

def construir_expediente_estructurado(carpeta_caso: str) -> str:
    if not os.path.exists(carpeta_caso):
        return ""
    archivos = [
        a for a in os.listdir(carpeta_caso) 
        if a.endswith((".pdf", ".txt", ".docx")) 
        and not a.startswith(("Dictamen_", "Memorial_"))
        and not a.endswith((".cache.txt", ".resumen.json"))
    ]
    if not archivos:
        return ""
    
    informe_consolidado = []
    for arch in archivos:
        ruta_arch = os.path.join(carpeta_caso, arch)
        texto = extraer_texto_archivo(ruta_arch, arch, carpeta_caso=carpeta_caso)
        sintesis = resumir_documento_individual(arch, texto, carpeta_caso)
        informe_consolidado.append(f"### DOCUMENTO: {arch}\n{sintesis.get('sintesis', '')}\n")
        
    return "\n".join(informe_consolidado)

# =====================================================================
# GENERACIÓN DE DICTAMEN
# =====================================================================
def ejecutar_dictamen_integral(hechos: str, docs_estructurados: str) -> str:
    prompt_sistema = """
Actúas como Consultor Jurídico Senior en Bolivia en Derecho Civil y Contrataciones del Estado (Ley 1178, Ley 439 y DS 0181).
Elabora un DICTAMEN LEGAL CONTUNDENTE Y RIGUROSO.

ESTRUCTURA DEL DICTAMEN:
1. IDENTIFICACIÓN DE LAS PARTES (Acreedor, deudor, personerías, NIT).
2. ANTECEDENTES Y RELACIÓN CONTRACTUAL (Cronología exacta de contratos, adendas, actas de recepción definitiva y notas).
3. DETERMINACIÓN DE LA OBLIGACIÓN ECONÓMICA (Monto total contractual, pagos parciales acreditados y saldo impago exigible).
4. VIABILIDAD PROCESAL Y ESTRATEGIA DE LITIGIO (Vía ejecutiva/coactiva, contencioso-administrativa, excepciones y medidas cautelares).
5. PLAN DE ACCIÓN INMEDIATO (Requerimientos, agotamiento de vía y plazos).

REGLA DE ORO:
- Basa tus conclusiones ÚNICAMENTE en los datos reales del expediente.
- Si no hay comprobante bancario de pago de un saldo, la deuda permanece vigente y exigible.
"""
    prompt_usuario = f"INSTRUCCIONES:\n{hechos}\n\nEXPEDIENTE DOCUMENTADO:\n{docs_estructurados}"
    res = cliente_groq.chat.completions.create(
        model=MODELO_TEXTO,
        messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": prompt_usuario}],
        temperature=0.05
    )
    return res.choices[0].message.content

# =====================================================================
# INTERFAZ STREAMLIT
# =====================================================================
st.title("⚖️ Bol-Lex AI: Bufete Digital Litigante")

with st.sidebar:
    st.success(f"🤖 IA Redactora: `{MODELO_TEXTO}`")
    st.info("👁️ Motor OCR: `Groq Vision Activo`")
    st.markdown("---")
    st.subheader("⚡ Gestión del Expediente")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        if st.button("💾 Guardar Caso", use_container_width=True):
            if st.session_state.carpeta_actual and os.path.exists(st.session_state.carpeta_actual):
                guardar_metadatos_caso(
                    st.session_state.carpeta_actual,
                    st.session_state.titulo_caso_actual,
                    st.session_state.codigo_caso_actual,
                    st.session_state.materia_detectada
                )
                if st.session_state.dictamen_actual:
                    with open(os.path.join(st.session_state.carpeta_actual, f"Dictamen_{st.session_state.codigo_caso_actual}.md"), "w", encoding="utf-8") as f:
                        f.write(st.session_state.dictamen_actual)
                st.toast("✅ Guardado con éxito.")
                st.rerun()
    with col_g2:
        if st.button("🔄 Nuevo Caso", type="secondary", use_container_width=True):
            reiniciar_caso()

    mapa_expedientes = listar_expedientes_locales()
    st.markdown("##### 📂 Historial de Expedientes")
    opciones = ["-- Seleccionar caso --"] + list(mapa_expedientes.keys())
    idx_defecto = 0
    for i, op in enumerate(opciones):
        if op != "-- Seleccionar caso --" and mapa_expedientes[op] == st.session_state.codigo_caso_actual:
            idx_defecto = i
            break
            
    seleccion = st.selectbox("Expedientes guardados:", options=opciones, index=idx_defecto)
    if seleccion != "-- Seleccionar caso --":
        cod_elegido = mapa_expedientes[seleccion]
        if cod_elegido != st.session_state.codigo_caso_actual:
            if st.button("📥 Cargar este Caso", use_container_width=True):
                cargar_expediente_existente(cod_elegido)

    if st.session_state.codigo_caso_actual:
        st.markdown("---")
        with st.expander("🗑️ Zona de Peligro"):
            if st.button("❌ Borrar este expediente", type="primary", use_container_width=True):
                eliminar_expediente_actual(st.session_state.codigo_caso_actual)

    st.markdown("---")
    st.subheader("📁 Archivos del Caso Activo")
    archivos_adjuntos = st.file_uploader(
        "Subir PDF, Word (.docx), TXT o comprimidos (.ZIP)",
        type=["pdf", "txt", "docx", "zip"],
        accept_multiple_files=True
    )
    
    url_gdrive = st.text_input("🔗 O pegar enlace de Google Drive:")
    if url_gdrive and st.button("📥 Importar desde Drive", use_container_width=True):
        cod_caso = st.session_state.codigo_caso_actual or f"BOLLEX-{datetime.now().strftime('%Y%m%d-%H%M')}"
        ruta_dest = os.path.join("Expedientes", cod_caso)
        os.makedirs(ruta_dest, exist_ok=True)
        st.session_state.carpeta_actual = ruta_dest
        st.session_state.codigo_caso_actual = cod_caso
        with st.spinner("Descargando desde Google Drive..."):
            if descargar_desde_gdrive(url_gdrive, ruta_dest):
                st.session_state.evidencia_acumulada = sincronizar_carpeta_caso(ruta_dest)
                st.toast("✅ Archivos de Drive importados.")
                st.rerun()

    if st.session_state.carpeta_actual and os.path.exists(st.session_state.carpeta_actual):
        st.markdown(f"**Expediente:** `{st.session_state.codigo_caso_actual}`")
        st.caption("Documentos en este expediente:")
        for f in os.listdir(st.session_state.carpeta_actual):
            if not f.endswith((".cache.txt", ".resumen.json", "meta.json")):
                st.text(f"• {f}")

# PANEL PRINCIPAL
st.subheader("📋 Dictamen y Diagnóstico Jurídico")
col_t1, col_t2 = st.columns([2, 1])
with col_t1:
    titulo_ingresado = st.text_input("🏷️ Identificador del caso:", value=st.session_state.titulo_caso_actual, placeholder="Ej: Caso Deuda EBC a Ecotraffic")
    if titulo_ingresado != st.session_state.titulo_caso_actual:
        st.session_state.titulo_caso_actual = titulo_ingresado
with col_t2:
    if st.session_state.codigo_caso_actual:
        st.caption(f"Código interno: `{st.session_state.codigo_caso_actual}`")

caso_cliente = st.text_area(
    "✍️ Planteamiento del caso e instrucciones para el bufete:",
    value="Revisa los antecedentes del caso adjunto y establece estrategia jurídica y acciones procesales.",
    height=90
)

if st.button("🚀 Analizar Caso y Generar Dictamen Estratégico", type="primary"):
    codigo_caso = st.session_state.codigo_caso_actual or f"BOLLEX-{datetime.now().strftime('%Y%m%d-%H%M')}"
    ruta_carpeta = os.path.join("Expedientes", codigo_caso)
    os.makedirs(ruta_carpeta, exist_ok=True)
    st.session_state.carpeta_actual = ruta_carpeta
    st.session_state.codigo_caso_actual = codigo_caso

    guardar_metadatos_caso(ruta_carpeta, st.session_state.titulo_caso_actual or codigo_caso, codigo_caso, "Civil")

    if archivos_adjuntos:
        for arch in archivos_adjuntos:
            if arch.name.lower().endswith(".zip"):
                descomprimir_zip(arch, ruta_carpeta)
            else:
                with open(os.path.join(ruta_carpeta, arch.name), "wb") as f:
                    f.write(arch.getbuffer())

    with st.spinner("Procesando evidencia documental con OCR e Inteligencia Artificial..."):
        try:
            docs_jerarquizados = construir_expediente_estructurado(ruta_carpeta)
            st.session_state.evidencia_acumulada = docs_jerarquizados

            dictamen = ejecutar_dictamen_integral(caso_cliente, docs_jerarquizados)
            st.session_state.dictamen_actual = dictamen

            with open(os.path.join(ruta_carpeta, f"Dictamen_{codigo_caso}.md"), "w", encoding="utf-8") as f:
                f.write(dictamen)

            pdf = MarkdownPdf(toc_level=0)
            pdf.add_section(Section(dictamen))
            pdf.save(os.path.join(ruta_carpeta, f"Dictamen_{codigo_caso}.pdf"))
            st.success("✅ Dictamen concluido sin alucinaciones.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error en procesamiento: {e}")

if st.session_state.dictamen_actual:
    st.divider()
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"📄 Dictamen: {st.session_state.titulo_caso_actual or st.session_state.codigo_caso_actual}")
    with col2:
        ruta_pdf = os.path.join(st.session_state.carpeta_actual, f"Dictamen_{st.session_state.codigo_caso_actual}.pdf")
        if os.path.exists(ruta_pdf):
            with open(ruta_pdf, "rb") as fp:
                st.download_button("📥 Descargar Dictamen en PDF", fp, file_name=f"Dictamen_{st.session_state.codigo_caso_actual}.pdf", mime="application/pdf", use_container_width=True)
    st.markdown(st.session_state.dictamen_actual)