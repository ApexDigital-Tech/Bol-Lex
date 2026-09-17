import os
import re
import time
import numpy as np
from datetime import datetime
import streamlit as st
from pypdf import PdfReader
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from groq import Groq

# Configuración de la página web
st.set_page_config(page_title="Bol-Lex AI", page_icon="⚖️", layout="wide")

# =====================================================================
# 1. PARSER Y MOTOR RAG
# =====================================================================
def extraer_datos_pdf(ruta_pdf: str) -> dict:
    reader = PdfReader(ruta_pdf)
    texto = "\n".join([p.extract_text() or "" for p in reader.pages])
    match_scp = re.search(r"SENTENCIA CONSTITUCIONAL PLURINACIONAL\s+([0-9]{3,4}/[0-9]{4}-[A-Z0-9]+)", texto, re.IGNORECASE)
    scp_numero = f"SCP {match_scp.group(1).strip()}" if match_scp else os.path.basename(ruta_pdf)
    match_sala = re.search(r"(SALA\s+[A-ZÁÉÍÓÚ\s]+)", texto[:2000], re.IGNORECASE)
    sala = match_sala.group(1).strip() if match_sala else "Sala Plena"
    patron_ratio = re.search(r"(III\.\s*FUNDAMENTOS\s+JUR[IÍ]DICOS\s+DEL\s+FALLO.*?)(POR\s+TANTO)", texto, re.DOTALL | re.IGNORECASE)
    ratio = patron_ratio.group(1).replace("III. FUNDAMENTOS JURÍDICOS DEL FALLO", "").strip() if patron_ratio else texto[:1500]
    return {"archivo": os.path.basename(ruta_pdf), "scp_numero": scp_numero, "sala": sala, "ratio_decidendi": ratio}

class MotorRAG:
    def __init__(self, carpeta: str = "sentencias_pdf"):
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.docs = []
        if os.path.exists(carpeta):
            self.docs = [extraer_datos_pdf(os.path.join(carpeta, arch)) for arch in os.listdir(carpeta) if arch.endswith(".pdf")]
        self.vectores = self.encoder.encode([d["ratio_decidendi"] for d in self.docs]) if self.docs else []
    
    def buscar(self, consulta: str) -> dict:
        if not self.docs:
            return {"scp_numero": "Ninguna", "sala": "-", "ratio_decidendi": "No hay PDFs.", "score": 0.0}
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
    cliente = Groq()
    lista = cliente.models.list()
    validos = [m.id for m in lista.data if "guard" not in m.id.lower() and "whisper" not in m.id.lower() and "orpheus" not in m.id.lower()]
    preferidos = [m for m in validos if "llama" in m.lower() or "gemma" in m.lower()]
    return cliente, (preferidos[0] if preferidos else validos[0])

# =====================================================================
# 2. PROMPTS ACTUALIZADOS (Con Sección Conclusiva)
# =====================================================================
PROMPTS_ESPECIALISTAS = {
    "Laboral": "Actúas como Abogado Laboralista boliviano. Te riges por la Ley General del Trabajo y Código Procesal del Trabajo.",
    "Penal": "Actúas como Abogado Penalista boliviano. Te riges por el Código Penal, el CPP (Ley 1970) y la Ley 1173.",
    "Familia": "Actúas como Abogado de Familia boliviano. Tu norma es la Ley 603.",
    "Civil": "Actúas como Abogado Civil y Comercial boliviano. Dominas el Código Civil y Procesal Civil.",
    "Constitucional": "Actúas como Constitucionalista boliviano. Tu marco es la CPE y la Ley 254."
}

def agente_director(hechos: str, cliente_ia, modelo: str) -> str:
    prompt = f'Lee este caso: "{hechos}". ¿A qué área del derecho boliviano corresponde? Responde SOLO con una palabra: Laboral, Penal, Familia, Civil, Constitucional.'
    try:
        res = cliente_ia.chat.completions.create(model=modelo, messages=[{"role": "user", "content": prompt}], temperature=0.0)
        materia = res.choices[0].message.content.strip().replace(".", "")
        return materia if materia in PROMPTS_ESPECIALISTAS else "Constitucional"
    except:
        return "Laboral"

def agente_especialista(hechos: str, scp_datos: dict, materia: str, documentos: str, cliente_ia, modelo: str) -> str:
    prompt_sistema = f"""
    {PROMPTS_ESPECIALISTAS.get(materia, PROMPTS_ESPECIALISTAS['Constitucional'])}
    Redacta un DICTAMEN JURÍDICO riguroso en formato Markdown.
    
    ESTRUCTURA OBLIGATORIA:
    1. SÍNTESIS DE LOS HECHOS Y PRUEBAS
    2. CALIFICACIÓN LEGAL Y NORMATIVA APLICABLE
    3. ANÁLISIS DE LA JURISPRUDENCIA (Subsunción al caso)
    4. ESTRATEGIA PROCESAL (Paso a paso)
    5. CONCLUSIÓN Y RECOMENDACIÓN FINAL (Firme, clara y orientada a la acción)
    """
    prompt_usuario = f"HECHOS:\n{hechos}\n\nDOCUMENTOS ADJUNTOS:\n{documentos}\n\nJURISPRUDENCIA:\n{scp_datos['ratio_decidendi']}"
    try:
        res = cliente_ia.chat.completions.create(model=modelo, messages=[{"role": "system", "content": prompt_sistema}, {"role": "user", "content": prompt_usuario}], temperature=0.3)
        return res.choices[0].message.content
    except Exception as e:
        return f"❌ Error del especialista: {e}"

# =====================================================================
# 3. INTERFAZ GRÁFICA Y GESTIÓN DE CARPETAS
# =====================================================================
st.title("⚖️ Bol-Lex AI: Bufete Digital")

motor_rag = cargar_motor()
cliente_groq, modelo_activo = obtener_modelo_ia()

# Panel Lateral
with st.sidebar:
    st.success(f"🤖 IA Activa: `{modelo_activo}`")
    st.info(f"📚 Precedentes: `{len(motor_rag.docs)} sentencias`")
    st.markdown("---")
    st.markdown("### 📁 Subir Evidencia")
    archivos_adjuntos = st.file_uploader("Adjunta PDFs o TXTs", accept_multiple_files=True)

# Cuerpo Principal
caso_cliente = st.text_area("✍️ Describe los hechos del caso:", height=150)

if st.button("🚀 Crear Expediente y Generar Dictamen", type="primary"):
    if len(caso_cliente) < 10:
        st.warning("⚠️ Describe el caso con más detalle.")
    else:
        # 1. Crear Código y Carpeta del Caso
        codigo_caso = f"BOLLEX-{datetime.now().strftime('%Y%m%d-%H%M')}"
        ruta_carpeta = os.path.join("Expedientes", codigo_caso)
        os.makedirs(ruta_carpeta, exist_ok=True)
        
        nombres_docs = ""
        # 2. Guardar Documentos Adjuntos
        if archivos_adjuntos:
            nombres_docs = ", ".join([a.name for a in archivos_adjuntos])
            for arch in archivos_adjuntos:
                with open(os.path.join(ruta_carpeta, arch.name), "wb") as f:
                    f.write(arch.getbuffer())

        with st.status(f"🗂️ Procesando Expediente {codigo_caso}...", expanded=True) as status:
            materia = agente_director(caso_cliente, cliente_groq, modelo_activo)
            st.write(f"✔️ Director: Caso asignado a **{materia.upper()}**")
            time.sleep(3)
            
            scp = motor_rag.buscar(caso_cliente)
            st.write(f"✔️ Archivo: Precedente **{scp['scp_numero']}** recuperado")
            time.sleep(3)

            st.write("💼 Especialista: Redactando dictamen con sección conclusiva...")
            dictamen = agente_especialista(caso_cliente, scp, materia, nombres_docs, cliente_groq, modelo_activo)
            
            # 3. Guardar el Dictamen en la Carpeta
            ruta_dictamen = os.path.join(ruta_carpeta, f"Dictamen_{codigo_caso}.md")
            with open(ruta_dictamen, "w", encoding="utf-8") as f:
                f.write(dictamen)
                
            status.update(label="✅ Expediente Finalizado", state="complete", expanded=False)

        st.success(f"📁 **EXPEDIENTE CREADO:** Todos los archivos y el dictamen se guardaron en la carpeta `/Expedientes/{codigo_caso}/` en tu computadora.")
        
        st.divider()
        st.subheader(f"📄 Dictamen Oficial - {codigo_caso}")
        st.markdown(dictamen)