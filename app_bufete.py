import io
import os
import re
import json
import shutil
import zipfile
import subprocess
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

# Control de hilos en CPU
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

# =====================================================================
# MOTOR OCR NATIVO
# =====================================================================
OCR_DISPONIBLE = False
try:
    from rapidocr_onnxruntime import RapidOCR
    import pypdfium2 as pdfium
    motor_ocr = RapidOCR()
    OCR_DISPONIBLE = True
except Exception:
    OCR_DISPONIBLE = False

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
        if nom_corto and nom_corto != c:
            etiqueta = f"{nom_corto} — [{c}]"
        else:
            etiqueta = c
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
    if os.path.exists(ruta_dictamen_md):
        with open(ruta_dictamen_md, "r", encoding="utf-8") as f:
            st.session_state.dictamen_actual = f.read()
    else:
        st.session_state.dictamen_actual = ""
        
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
# MOTOR RAG LOCAL
# =====================================================================
def extraer_datos_pdf(ruta_pdf: str) -> dict:
    try:
        reader = PdfReader(ruta_pdf)
        texto = "\n".join([p.extract_text() or "" for p in reader.pages])
    except Exception:
        texto = ""
    match_scp = re.search(r"SENTENCIA CONSTITUCIONAL PLURINACIONAL\s+([0-9]{3,4}/[0-9]{4}-[A-Z0-9]+)", texto, re.IGNORECASE)
    scp_numero = f"SCP {match_scp.group(1).strip()}" if match_scp else os.path.basename(ruta_pdf)
    match_sala = re.search(r"(SALA\s+[A-ZÁÉÍÓÚ\s]+)", texto[:2000], re.IGNORECASE)
    sala = match_sala.group(1).strip() if match_sala else "Sala Plena"
    patron_ratio = re.search(r"(III\.\s*FUNDAMENTOS\s+JUR[IÍ]DICOS\s+DEL\s+FALLO.*?)(POR\s+TANTO)", texto, re.DOTALL | re.IGNORECASE)
    ratio = patron_ratio.group(1).replace("III. FUNDAMENTOS JURÍDICOS DEL FALLO", "").strip() if patron_ratio else texto[:1500]
    return {"archivo": os.path.basename(ruta_pdf), "scp_numero": scp_numero, "sala": sala, "ratio_decidendi": ratio}

class MotorRAG:
    def __init__(self, carpeta: str = "sentencias_pdf"):
        from sentence_transformers import SentenceTransformer
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.docs = []
        if os.path.exists(carpeta):
            self.docs = [extraer_datos_pdf(os.path.join(carpeta, arch)) for arch in os.listdir(carpeta) if arch.endswith(".pdf")]
        self.vectores = self.encoder.encode([d["ratio_decidendi"] for d in self.docs]) if self.docs else []
    
    def buscar(self, consulta: str) -> dict:
        if not self.docs:
            return {"scp_numero": "Ninguna", "sala": "-", "ratio_decidendi": "Sin jurisprudencia local indexada.", "score": 0.0}
        v_q = self.encoder.encode([consulta])
        sims = cosine_similarity(v_q, self.vectores)[0]
        idx = int(np.argmax(sims))
        res = self.docs[idx].copy()
        res["score"] = float(sims[idx])
        return res

@st.cache_resource
def cargar_motor():
    return MotorRAG("sentencias_pdf")

@st.cache_resource
def obtener_modelo_ia():
    api_key = os.environ.get("GROQ_API_KEY", "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")
    cliente = Groq(api_key=api_key)
    
    # Lista prioritaria estricta de modelos de producción sin restricciones de términos
    modelos_prioritarios = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768"
    ]
    
    modelo_elegido = "llama-3.1-8b-instant"
    try:
        lista_activos = [m.id for m in cliente.models.list().data]
        for candidato in modelos_prioritarios:
            if candidato in lista_activos:
                modelo_elegido = candidato
                break
    except Exception:
        modelo_elegido = "llama-3.1-8b-instant"
        
    return cliente, modelo_elegido

# =====================================================================
# EXTRACTOR DOCUMENTAL CON OCR
# =====================================================================
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
                ruta_cache = os.path.join(carpeta_caso, f"{nombre}.ocr_cache.txt")
                if os.path.exists(ruta_cache):
                    with open(ruta_cache, "r", encoding="utf-8") as fc:
                        return fc.read()

            reader = PdfReader(ruta_o_buffer)
            paginas = [p.extract_text() or "" for p in reader.pages]
            texto_digital = "\n".join(paginas).strip()
            
            if len(texto_digital) > 80:
                if carpeta_caso:
                    with open(os.path.join(carpeta_caso, f"{nombre}.ocr_cache.txt"), "w", encoding="utf-8") as fc:
                        fc.write(texto_digital)
                return texto_digital

            if OCR_DISPONIBLE:
                st.toast(f"🔍 OCR en: {nombre}...")
                if isinstance(ruta_o_buffer, str):
                    doc_pdf = pdfium.PdfDocument(ruta_o_buffer)
                else:
                    ruta_o_buffer.seek(0)
                    doc_pdf = pdfium.PdfDocument(ruta_o_buffer.read())
                
                texto_ocr = []
                limite_pags = min(len(doc_pdf), 6)
                for idx in range(limite_pags):
                    page = doc_pdf[idx]
                    bitmap = page.render(scale=1.4)
                    pil_img = bitmap.to_pil().convert("RGB")
                    img_array = np.array(pil_img)
                    
                    resultado, _ = motor_ocr(img_array)
                    if resultado:
                        lineas = [linea[1] for linea in resultado if linea[1].strip()]
                        if lineas:
                            texto_ocr.append(f"[Página {idx+1}]\n" + "\n".join(lineas))
                
                resultado_final = "\n".join(texto_ocr)
                if resultado_final.strip():
                    if carpeta_caso:
                        with open(os.path.join(carpeta_caso, f"{nombre}.ocr_cache.txt"), "w", encoding="utf-8") as fc:
                            fc.write(resultado_final)
                    return resultado_final
            
            return f"[Archivo escaneado {nombre}: texto ilegible o sin OCR]."
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
            and not a.endswith((".ocr_cache.txt", ".resumen.json"))
        ]
        for arch in archivos:
            ruta_completa = os.path.join(ruta_carpeta, arch)
            texto = extraer_texto_archivo(ruta_completa, arch, carpeta_caso=ruta_carpeta)
            acumulado += f"\n--- DOCUMENTO: {arch} ---\n{texto[:3500].strip()}\n"
    return acumulado

# =====================================================================
# ANÁLISIS DOCUMENTAL JERÁRQUICO (MAP-REDUCE ANTI-ALUCINACIÓN)
# =====================================================================
def resumir_documento_individual(nombre_archivo: str, texto: str, cliente_ia, modelo: str, carpeta_caso: str) -> dict:
    """Extrae hechos probados, fechas, montos y partes de cada documento para evitar saturar el LLM."""
    ruta_resumen = os.path.join(carpeta_caso, f"{nombre_archivo}.resumen.json")
    if os.path.exists(ruta_resumen):
        try:
            with open(ruta_resumen, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    prompt_extract = f"""
Analiza este documento del expediente boliviano de manera estricta y extrae solo hechos comprobados:
DOCUMENTO: {nombre_archivo}
CONTENIDO:
{texto[:5000]}

Responde en formato de texto breve:
1. Tipo de documento y fecha:
2. Partes identificadas (Nombres / Entidades exactas):
3. Objeto principal o contrato referenciado:
4. Montos económicos específicos (si existen, con moneda exacta):
5. Estado o situación de cumplimiento/deuda:
REGLA: Si un dato no figura en el texto, escribe 'No especificado'. NO asumas ni inventes nada.
"""
    try:
        res = cliente_ia.chat.completions.create(
            model=modelo,
            messages=[{"role": "user", "content": prompt_extract}],
            temperature=0.0
        )
        resumen = res.choices[0].message.content.strip()
        datos = {"archivo": nombre_archivo, "sintesis": resumen}
        with open(ruta_resumen, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        return datos
    except Exception:
        return {"archivo": nombre_archivo, "sintesis": texto[:500]}

def construir_expediente_estructurado(carpeta_caso: str, cliente_ia, modelo: str) -> str:
    """Consolida la síntesis de todos los documentos del expediente."""
    if not os.path.exists(carpeta_caso):
        return ""
    archivos = [
        a for a in os.listdir(carpeta_caso) 
        if a.endswith((".pdf", ".txt", ".docx")) 
        and not a.startswith(("Dictamen_", "Memorial_"))
        and not a.endswith((".ocr_cache.txt", ".resumen.json"))
    ]
    if not archivos:
        return ""
    
    informe_consolidado = []
    for arch in archivos:
        ruta_arch = os.path.join(carpeta_caso, arch)
        texto = extraer_texto_archivo(ruta_arch, arch, carpeta_caso=carpeta_caso)
        sintesis = resumir_documento_individual(arch, texto, cliente_ia, modelo, carpeta_caso)
        informe_consolidado.append(f"### [DOCUMENTO]: {arch}\n{sintesis.get('sintesis', '')}\n")
        
    return "\n".join(informe_consolidado)

# =====================================================================
# GENERADOR WORD FORENSE (.DOCX)
# =====================================================================
def exportar_memorial_docx(texto_md: str, ruta_salida: str):
    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.3)
        section.right_margin = Inches(0.8)

    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Times New Roman'
    normal_style.font.size = Pt(12)
    normal_style.font.color.rgb = RGBColor(0, 0, 0)

    for linea in texto_md.split("\n"):
        l = linea.strip()
        if not l:
            continue
        if l.startswith("# "):
            p = doc.add_paragraph()
            run = p.add_run(l.replace("# ", ""))
            run.bold = True
            run.font.size = Pt(14)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif l.startswith("## "):
            p = doc.add_paragraph()
            run = p.add_run(l.replace("## ", ""))
            run.bold = True
            run.font.size = Pt(12)
            p.paragraph_format.space_before = Pt(10)
        elif l.startswith("### "):
            p = doc.add_paragraph()
            run = p.add_run(l.replace("### ", ""))
            run.bold = True
        elif l.startswith("SEÑOR JUEZ") or l.startswith("SUMA:"):
            p = doc.add_paragraph()
            run = p.add_run(l.replace("**", ""))
            run.bold = True
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(8)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.line_spacing = 1.15
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(4)
            partes = re.split(r'(\*\*.*?\*\*)', l)
            for parte in partes:
                if parte.startswith("**") and parte.endswith("**"):
                    r = p.add_run(parte[2:-2])
                    r.bold = True
                else:
                    p.add_run(parte)

    doc.save(ruta_salida)

# =====================================================================
# AGENTES Y DICTAMEN INTEGRAL
# =====================================================================
MATERIAS_CONFIG = {
    "Civil": "Civil y Comercial (Ley 439 y Código Civil). Cobros ejecutivos, contratos y obligaciones.",
    "Laboral": "Laboral y Seguridad Social (Ley General del Trabajo y DS 28699).",
    "Penal": "Penal y Procesal Penal (Código Penal y Ley 1970).",
    "Familia": "Familiar (Ley 603 Código de las Familias).",
    "Constitucional": "Constitucional (CPE y Ley 254). Amparos y Acciones Populares."
}

def clasificar_materia(hechos: str, cliente_ia, modelo: str) -> str:
    prompt = f'Clasifica la materia jurídica: "{hechos[:600]}". Responde con UNA sola palabra exacta: Civil, Laboral, Penal, Familia o Constitucional.'
    try:
        res = cliente_ia.chat.completions.create(model=modelo, messages=[{"role": "user", "content": prompt}], temperature=0.0)
        resp = res.choices[0].message.content.strip().replace(".", "")
        for m in MATERIAS_CONFIG.keys():
            if m.lower() in resp.lower():
                return m
        return "Civil"
    except Exception:
        return "Civil"

def ejecutar_dictamen_integral(hechos: str, scp: dict, docs_estructurados: str, materia: str, cliente_ia, modelo: str) -> str:
    if len(docs_estructurados.strip()) < 50:
        return """# ⚠️ ERROR DE LECTURA DOCUMENTAL
No se detectó contenido suficiente en el expediente activo. Verifique haber subido los archivos o haber presionado 'Importar desde Drive'.
"""

    prompt_sistema = f"""
Actúas como Consultor Jurídico Senior en Bolivia en materia {MATERIAS_CONFIG.get(materia, MATERIAS_CONFIG['Civil'])}.
Elabora un dictamen CONTUNDENTE, TÉCNICO y APEGADO ESTRICTAMENTE A LOS HECHOS PROBADOS del expediente.

ESTRUCTURA OBLIGATORIA:
1. IDENTIFICACIÓN DE LAS PARTES (Acreedor, deudor, garantes, personería jurídica).
2. ANTECEDENTES Y RELACIÓN CONTRACTUAL (Detalle cronológico de contratos, adendas, notas y cartas notariales).
3. DETERMINACIÓN DE LA OBLIGACIÓN ECONÓMICA (Montos reales devengados, pagos acreditados y saldo impago exigible).
4. VIABILIDAD PROCESAL Y ESTRATEGIA DE LITIGIO (Vía monitoria ejecutiva, proceso ordinario o excepciones).
5. PLAN DE ACCIÓN INMEDIATO (Requerimientos, medidas precautorias y plazos procesales).

REGLAS DE SEGURIDAD JURÍDICA:
- Queda terminantemente prohibido asumir o inventar que una deuda fue pagada si no existe un recibo bancario o comprobante expreso en los antecedentes.
- Consigna las fechas y números de contrato exactamente como constan en la documentación.
"""
    prompt_usuario = f"INSTRUCCIONES DEL CLIENTE:\n{hechos}\n\nEXPEDIENTE DOCUMENTADO:\n{docs_estructurados}\n\nJURISPRUDENCIA:\n{scp.get('ratio_decidendi', '')}"
    res = cliente_ia.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": prompt_usuario}],
        temperature=0.05
    )
    return res.choices[0].message.content

def redactar_memorial_forense(hechos: str, docs: str, borrador_usuario: str, materia: str, abogado: str, cliente_ia, modelo: str) -> str:
    prompt_sistema = f"""
Actúas como el Abogado Litigante patrocinante ({abogado}) en Bolivia.
Redacta un MEMORIAL FORENSE COMPLETO reglamentario boliviano (Suma, Autoridad Judicial, Generales, Hechos, Fundamento de Derecho, Petitorio, Otrosíes).
Materia: {materia}.
"""
    prompt_usuario = f"INSTRUCCIONES:\n{hechos}\n\nEXPEDIENTE:\n{docs}\n\nBORRADOR PREVIO:\n{borrador_usuario if borrador_usuario else 'Memorial íntegro.'}"
    res = cliente_ia.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": prompt_usuario}],
        temperature=0.1
    )
    return res.choices[0].message.content

def relacionar_todos_los_casos(cliente_ia, modelo: str) -> str:
    mapa = listar_expedientes_locales()
    if not mapa:
        return "No hay expedientes registrados para relacionar."
    
    resumen_global = ""
    for etiq, cod in mapa.items():
        ruta = os.path.join("Expedientes", cod)
        ruta_dict = os.path.join(ruta, f"Dictamen_{cod}.md")
        resumen_dict = "Sin dictamen generado aún."
        if os.path.exists(ruta_dict):
            with open(ruta_dict, "r", encoding="utf-8") as f:
                resumen_dict = f.read()[:1000]
        resumen_global += f"\n=== EXPEDIENTE: {etiq} ===\n{resumen_dict}\n"

    prompt = f"""
Actúas como el Director General del Bufete Jurídico.
Analiza la totalidad de los expedientes del despacho y presenta un INFORME ESTRATÉGICO DE CONEXIDAD Y RELACIONES INTERCASOS.
OBJETIVOS: Identidad de sujetos, conexidad económica/deudas cruzadas y estrategia procesal integral.

EXPEDIENTES ACTIVOS EN EL BUFETE:
{resumen_global}
"""
    res = cliente_ia.chat.completions.create(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return res.choices[0].message.content

# =====================================================================
# INTERFAZ STREAMLIT
# =====================================================================
st.title("⚖️ Bol-Lex AI: Bufete Digital Litigante")

motor_rag = cargar_motor()
cliente_groq, modelo_activo = obtener_modelo_ia()

with st.sidebar:
    st.success(f"🤖 IA Redactora: `{modelo_activo}`")
    st.info(f"📚 Precedentes RAG: `{len(motor_rag.docs)} sentencias`")
    if OCR_DISPONIBLE:
        st.success("👁️ Motor OCR: `RapidOCR ONNX Activo`")
    else:
        st.warning("⚠️ OCR Local no disponible")
    
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
                if st.session_state.memorial_actual:
                    ruta_mem = os.path.join(st.session_state.carpeta_actual, f"Memorial_{st.session_state.codigo_caso_actual}.docx")
                    exportar_memorial_docx(st.session_state.memorial_actual, ruta_mem)
                st.toast("✅ Expediente y metadatos guardados.")
                st.rerun()
            else:
                st.toast("⚠️ No hay expediente activo.")
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
            st.caption(f"Eliminar expediente `{st.session_state.codigo_caso_actual}`")
            if st.button("❌ Borrar este caso de prueba", type="primary", use_container_width=True):
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
                st.toast("✅ Archivos de Drive importados con éxito.")
                st.rerun()

    if st.session_state.carpeta_actual and os.path.exists(st.session_state.carpeta_actual):
        st.markdown(f"**Expediente:** `{st.session_state.codigo_caso_actual}`")
        if st.button("🔄 Sincronizar archivos", use_container_width=True):
            st.session_state.evidencia_acumulada = sincronizar_carpeta_caso(st.session_state.carpeta_actual)
            st.toast("Archivos sincronizados.")

        st.caption("Documentos en este expediente:")
        for f in os.listdir(st.session_state.carpeta_actual):
            if not f.endswith((".ocr_cache.txt", ".resumen.json", "meta.json")):
                st.text(f"• {f}")

tab1, tab2, tab3, tab4 = st.tabs(["📋 Dictamen y Diagnóstico", "📝 Redactor de Memorial (Word / PDF)", "💬 Consultorio Jurídico y Relación Intercasos", "🗄️ Archivo Documental"])

with tab1:
    col_t1, col_t2 = st.columns([2, 1])
    with col_t1:
        titulo_ingresado = st.text_input(
            "🏷️ Nombre corto identificador del caso:",
            value=st.session_state.titulo_caso_actual,
            placeholder="Ej: Caso Deuda EBC a Ecotraffic / Demanda Ribepar"
        )
        if titulo_ingresado != st.session_state.titulo_caso_actual:
            st.session_state.titulo_caso_actual = titulo_ingresado
    with col_t2:
        st.write("")
        st.write("")
        if st.session_state.codigo_caso_actual:
            st.caption(f"Código interno: `{st.session_state.codigo_caso_actual}`")

    caso_cliente = st.text_area(
        "✍️ Planteamiento del caso e instrucciones para el bufete:",
        value="" if not st.session_state.dictamen_actual else "Revisa los antecedentes del caso adjunto y establece estrategia jurídica y acciones procesales.",
        placeholder="Describe aquí el caso o las instrucciones específicas...",
        height=90
    )

    if st.button("🚀 Analizar Caso y Generar Dictamen Estratégico", type="primary"):
        codigo_caso = st.session_state.codigo_caso_actual or f"BOLLEX-{datetime.now().strftime('%Y%m%d-%H%M')}"
        ruta_carpeta = os.path.join("Expedientes", codigo_caso)
        os.makedirs(ruta_carpeta, exist_ok=True)
        st.session_state.carpeta_actual = ruta_carpeta
        st.session_state.codigo_caso_actual = codigo_caso

        guardar_metadatos_caso(
            ruta_carpeta,
            st.session_state.titulo_caso_actual or codigo_caso,
            codigo_caso,
            st.session_state.materia_detectada
        )

        if archivos_adjuntos:
            for arch in archivos_adjuntos:
                if arch.name.lower().endswith(".zip"):
                    descomprimir_zip(arch, ruta_carpeta)
                else:
                    ruta_arch = os.path.join(ruta_carpeta, arch.name)
                    with open(ruta_arch, "wb") as f:
                        f.write(arch.getbuffer())

        with st.spinner("Procesando y jerarquizando documentos del expediente..."):
            try:
                # Paso 1: Jerarquizar cada archivo individualmente (Map-Reduce)
                docs_jerarquizados = construir_expediente_estructurado(ruta_carpeta, cliente_groq, modelo_activo)
                st.session_state.evidencia_acumulada = docs_jerarquizados

                # Paso 2: Clasificar materia y buscar jurisprudencia
                materia = clasificar_materia(caso_cliente + "\n" + docs_jerarquizados[:1000], cliente_groq, modelo_activo)
                st.session_state.materia_detectada = materia
                scp = motor_rag.buscar(caso_cliente)
                
                # Paso 3: Generar dictamen fundamentado
                dictamen = ejecutar_dictamen_integral(caso_cliente, scp, docs_jerarquizados, materia, cliente_groq, modelo_activo)
                st.session_state.dictamen_actual = dictamen

                with open(os.path.join(ruta_carpeta, f"Dictamen_{codigo_caso}.md"), "w", encoding="utf-8") as f:
                    f.write(dictamen)

                pdf = MarkdownPdf(toc_level=0)
                pdf.add_section(Section(dictamen))
                pdf.save(os.path.join(ruta_carpeta, f"Dictamen_{codigo_caso}.pdf"))
                st.success("✅ Dictamen procesado y guardado.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error en procesamiento: {e}")

    if st.session_state.dictamen_actual:
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            titulo_mostrar = st.session_state.titulo_caso_actual or st.session_state.codigo_caso_actual
            st.subheader(f"📄 Dictamen: {titulo_mostrar} ({st.session_state.materia_detectada})")
        with col2:
            ruta_pdf = os.path.join(st.session_state.carpeta_actual, f"Dictamen_{st.session_state.codigo_caso_actual}.pdf")
            if os.path.exists(ruta_pdf):
                with open(ruta_pdf, "rb") as fp:
                    st.download_button("📥 Descargar Dictamen en PDF", fp, file_name=f"Dictamen_{st.session_state.codigo_caso_actual}.pdf", mime="application/pdf", use_container_width=True)
        st.markdown(st.session_state.dictamen_actual)

with tab2:
    st.subheader("📝 Redactor Forense de Memoriales (Word .docx y PDF)")
    col_ab1, col_ab2 = st.columns([2, 1])
    with col_ab1:
        abogado_firmante = st.text_input("Abogado patrocinante:", value="Dr. Jhamil Sanchez - M.C.A. 45892")
    with col_ab2:
        tipo_accion = st.text_input("Tipo de memorial / Suma:", value="Demanda Ejecutiva / Contestación con Excepciones")

    borrador_subido = st.file_uploader("Adjuntar borrador previo (.txt o .docx):", type=["txt", "docx"], key="upload_borrador")
    texto_borrador_manual = st.text_area("O pega aquí notas complementarias:", height=100)

    if st.button("⚖️ Redactar Memorial Oficial en Formato Forense", type="primary"):
        with st.spinner("Redactando memorial forense en Word..."):
            try:
                borrador_final = ""
                if borrador_subido:
                    borrador_final += f"\n--- BORRADOR ADJUNTO ---\n{extraer_texto_archivo(borrador_subido, borrador_subido.name, st.session_state.carpeta_actual)}\n"
                if texto_borrador_manual:
                    borrador_final += f"\n--- NOTAS ADICIONALES ---\n{texto_borrador_manual}\n"

                mem_texto = redactar_memorial_forense(
                    caso_cliente + "\nSuma pretendida: " + tipo_accion,
                    st.session_state.evidencia_acumulada[:9000],
                    borrador_final,
                    st.session_state.materia_detectada,
                    abogado_firmante,
                    cliente_groq,
                    modelo_activo
                )
                st.session_state.memorial_actual = mem_texto

                if st.session_state.carpeta_actual:
                    ruta_mem_docx = os.path.join(st.session_state.carpeta_actual, f"Memorial_{st.session_state.codigo_caso_actual}.docx")
                    exportar_memorial_docx(mem_texto, ruta_mem_docx)
                st.success("✅ Memorial redactado y compilado en .docx.")
            except Exception as e:
                st.error(f"❌ Error redactando memorial: {e}")

    if st.session_state.memorial_actual:
        st.divider()
        col_m1, col_m2 = st.columns([2, 2])
        with col_m1:
            st.subheader("📄 Memorial Forense Generado")
        with col_m2:
            ruta_mem_docx = os.path.join(st.session_state.carpeta_actual, f"Memorial_{st.session_state.codigo_caso_actual}.docx")
            if os.path.exists(ruta_mem_docx):
                with open(ruta_mem_docx, "rb") as f_docx:
                    st.download_button(
                        label="📥 Descargar Memorial en Word (.docx)",
                        data=f_docx,
                        file_name=f"Memorial_{st.session_state.codigo_caso_actual}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary",
                        use_container_width=True
                    )
        st.markdown(st.session_state.memorial_actual)

with tab3:
    st.subheader("💬 Consultorio Jurídico y Relación Intercasos")
    
    st.markdown("#### 🔗 Informe del Agente Director: Relación y Conexidad Global")
    if st.button("🌐 Analizar Relación de Todos los Casos del Bufete", type="secondary"):
        with st.spinner("El Agente Director está analizando conexidad entre todos los expedientes..."):
            try:
                informe_cruzado = relacionar_todos_los_casos(cliente_groq, modelo_activo)
                st.markdown(informe_cruzado)
                st.divider()
            except Exception as e:
                st.error(f"Error generando análisis global: {e}")

    st.markdown("#### 🗨️ Consultas sobre el Caso Activo")
    for preg, resp in st.session_state.historial_consultas:
        with st.chat_message("user"):
            st.write(preg)
        with st.chat_message("assistant"):
            st.markdown(resp)

    pregunta = st.chat_input("Consulta jurídica sobre este caso...")
    if pregunta:
        with st.chat_message("user"):
            st.write(pregunta)
        
        prompt_chat = f"Dictamen previo:\n{st.session_state.dictamen_actual[:2500]}\n\nEvidencia:\n{st.session_state.evidencia_acumulada[:6000]}\n\nConsulta:\n{pregunta}"
        try:
            res_chat = cliente_groq.chat.completions.create(
                model=modelo_activo,
                messages=[{"role": "user", "content": prompt_chat}],
                temperature=0.1
            )
            resp_texto = res_chat.choices[0].message.content
            with st.chat_message("assistant"):
                st.markdown(resp_texto)
            st.session_state.historial_consultas.append((pregunta, resp_texto))
        except Exception as e:
            st.error(f"Error en consulta: {e}")

with tab4:
    st.subheader("🗄️ Archivo Documental del Expediente Activo")
    if not st.session_state.carpeta_actual or not os.path.exists(st.session_state.carpeta_actual):
        st.info("No hay un expediente activo cargado.")
    else:
        archivos_disco = [f for f in os.listdir(st.session_state.carpeta_actual) if not f.endswith((".ocr_cache.txt", ".resumen.json", "meta.json"))]
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("#### 📑 Documentos Elaborados por Bol-Lex")
            elaborados = [f for f in archivos_disco if f.startswith(("Dictamen_", "Memorial_"))]
            if elaborados:
                for arch in elaborados:
                    ruta_arch = os.path.join(st.session_state.carpeta_actual, arch)
                    with open(ruta_arch, "rb") as f_el:
                        st.download_button(
                            label=f"⬇️ Descargar {arch}",
                            data=f_el,
                            file_name=arch,
                            key=f"dl_el_{arch}"
                        )
            else:
                st.caption("Aún no se han generado dictámenes o memoriales para este expediente.")

        with col_d2:
            st.markdown("#### 📎 Documentos y Pruebas Adjuntas")
            adjuntos = [f for f in archivos_disco if not f.startswith(("Dictamen_", "Memorial_"))]
            if adjuntos:
                for arch in adjuntos:
                    ruta_arch = os.path.join(st.session_state.carpeta_actual, arch)
                    with open(ruta_arch, "rb") as f_adj:
                        st.download_button(
                            label=f"📎 Descargar {arch}",
                            data=f_adj,
                            file_name=arch,
                            key=f"dl_adj_{arch}"
                        )
            else:
                st.caption("No hay documentos adjuntos en la carpeta.")