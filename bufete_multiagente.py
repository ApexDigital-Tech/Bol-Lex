import os
import re
import time
import numpy as np
from pypdf import PdfReader
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from groq import Groq

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
        print("📚 [SISTEMA] Cargando archivo jurisprudencial...")
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.docs = [extraer_datos_pdf(os.path.join(carpeta, arch)) for arch in os.listdir(carpeta) if arch.endswith(".pdf")]
        self.vectores = self.encoder.encode([d["ratio_decidendi"] for d in self.docs])
    
    def buscar(self, consulta: str) -> dict:
        v_q = self.encoder.encode([consulta])
        sims = cosine_similarity(v_q, self.vectores)[0]
        idx = int(np.argmax(sims))
        res = self.docs[idx].copy()
        res["score"] = float(sims[idx])
        return res

# =====================================================================
# 2. CONFIGURACIÓN DE IA Y DICCIONARIO
# =====================================================================
def obtener_modelo_ia():
    cliente = Groq()
    lista_modelos = cliente.models.list()
    
    # Filtramos todo lo que sea audio, guardias o modelos que piden aceptar términos extra
    modelos_validos = [
        m.id for m in lista_modelos.data 
        if "guard" not in m.id.lower() 
        and "whisper" not in m.id.lower()
        and "orpheus" not in m.id.lower()
    ]
    
    # Buscamos preferentemente Llama o Gemma
    modelos_preferidos = [m for m in modelos_validos if "llama" in m.lower() or "gemma" in m.lower()]
    
    # Elegimos el primero de la lista que tu cuenta sí tenga habilitado
    modelo_activo = modelos_preferidos[0] if modelos_preferidos else modelos_validos[0]
        
    print(f"🤖 [SISTEMA] IA conectada. Modelo asignado automáticamente: {modelo_activo}")
    return cliente, modelo_activo

PROMPTS_ESPECIALISTAS = {
    "Laboral": "Actúas como Abogado Laboralista boliviano. Te riges por la Ley General del Trabajo, su Decreto Reglamentario y el Código Procesal del Trabajo. Tu enfoque es la protección de derechos sociolaborales (finiquitos, reincorporaciones, desahucios).",
    "Penal": "Actúas como Abogado Penalista bajo el sistema acusatorio boliviano. Te riges por el Código Penal, el CPP (Ley 1970) y la Ley 1173. Analizas tipicidad, riesgos procesales y salidas alternativas.",
    "Familia": "Actúas como Abogado de Familia boliviano. Tu norma es la Ley 603 (Código de las Familias). Priorizas el Interés Superior del Menor, liquidación de asistencia familiar y divorcios.",
    "Civil": "Actúas como Abogado Civil y Comercial boliviano. Dominas el Código Civil (Ley 12760) y el Código Procesal Civil (Ley 438). Analizas contratos, obligaciones, y procesos ordinarios/monitorios.",
    "Constitucional": "Actúas como Constitucionalista boliviano. Tu marco es la CPE y el Código Procesal Constitucional (Ley 254). Analizas acciones tutelares, subsidiariedad e inmediatez."
}

# =====================================================================
# 3. LOS AGENTES
# =====================================================================
def agente_director(hechos: str, cliente_ia, modelo: str) -> str:
    print("👔 [AGENTE DIRECTOR] Analizando los hechos para asignar el caso...")
    prompt = f"""
    Lee este caso legal: "{hechos}"
    ¿A qué área del derecho boliviano corresponde principalmente? 
    Responde ÚNICAMENTE con UNA de estas cinco palabras, sin explicaciones: Laboral, Penal, Familia, Civil, Constitucional.
    """
    try:
        res = cliente_ia.chat.completions.create(
            model=modelo,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        materia = res.choices[0].message.content.strip().replace(".", "")
        if materia not in PROMPTS_ESPECIALISTAS:
            materia = "Constitucional"
    except Exception as e:
        print(f"⚠️ [SISTEMA] Groq Rate Limit alcanzado. Forzando ruta a Laboral. Detalle: {e}")
        materia = "Laboral"
        
    print(f"👔 [AGENTE DIRECTOR] Caso asignado al departamento: {materia.upper()}")
    return materia

def agente_especialista(hechos: str, scp_datos: dict, materia: str, cliente_ia, modelo: str) -> str:
    print(f"💼 [ESPECIALISTA {materia.upper()}] Redactando dictamen especializado...")
    prompt_sistema = f"""
    {PROMPTS_ESPECIALISTAS.get(materia, PROMPTS_ESPECIALISTAS["Constitucional"])}
    
    Redacta un DICTAMEN JURÍDICO en base a los hechos y al precedente del TCP.
    Estructura:
    1. CALIFICACIÓN LEGAL (Desde la óptica {materia})
    2. APLICACIÓN DE LA LEY BOLIVIANA VIGENTE
    3. ANÁLISIS DE LA JURISPRUDENCIA (SCP {scp_datos['scp_numero']})
    4. ESTRATEGIA PROCESAL A SEGUIR
    """
    prompt_usuario = f"HECHOS:\n{hechos}\n\nJURISPRUDENCIA (Ratio Decidendi):\n{scp_datos['ratio_decidendi']}"
    
    try:
        res = cliente_ia.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            temperature=0.3
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"❌ Error del especialista: {e}"

# =====================================================================
# 4. ORQUESTACIÓN
# =====================================================================
if __name__ == "__main__":
    print("="*80)
    print("🏢 INICIANDO BUFETE MULTI-AGENTE (BOL-LEX)")
    print("="*80)
    
    motor_rag = MotorRAG("sentencias_pdf")
    cliente_groq, modelo_activo = obtener_modelo_ia()
    
    caso_cliente = (
        "Una trabajadora con 6 meses de embarazo fue despedida de la empresa Constructora del Sur "
        "sin que medie proceso. La Jefatura de Trabajo emitió Conminatoria de Reincorporación, "
        "pero el empleador le impide el ingreso."
    )
    
    print(f"\n📩 CASO NUEVO:\n\"{caso_cliente}\"\n")
    
    materia_asignada = agente_director(caso_cliente, cliente_groq, modelo_activo)
    
    print("⏳ [SISTEMA] Pausa de 5 segundos para no saturar a Groq...")
    time.sleep(5)
    
    scp_encontrada = motor_rag.buscar(caso_cliente)
    print(f"🔍 [ARCHIVO RAG] Precedente recuperado: {scp_encontrada['scp_numero']} (Similitud: {scp_encontrada['score']:.2f})")
    
    dictamen = agente_especialista(caso_cliente, scp_encontrada, materia_asignada, cliente_groq, modelo_activo)
    
    print("\n" + "="*80)
    print(f"📄 DICTAMEN FINAL DEL DEPARTAMENTO {materia_asignada.upper()}")
    print("="*80)
    print(dictamen)
    print("="*80)