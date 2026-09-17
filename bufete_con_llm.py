import os
import re
import json
import numpy as np
from pypdf import PdfReader
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from groq import Groq

# =====================================================================
# 1. PARSER DEL PDF DEL TCP
# =====================================================================
def extraer_datos_pdf(ruta_pdf: str) -> dict:
    reader = PdfReader(ruta_pdf)
    texto = "\n".join([p.extract_text() or "" for p in reader.pages])
    
    match_scp = re.search(r"SENTENCIA CONSTITUCIONAL PLURINACIONAL\s+([0-9]{3,4}/[0-9]{4}-[A-Z0-9]+)", texto, re.IGNORECASE)
    scp_numero = f"SCP {match_scp.group(1).strip()}" if match_scp else os.path.basename(ruta_pdf)

    match_sala = re.search(r"(SALA\s+[A-ZÁÉÍÓÚ\s]+)", texto[:2000], re.IGNORECASE)
    sala = match_sala.group(1).strip() if match_sala else "Sala Plena"

    patron_ratio = re.search(
        r"(III\.\s*FUNDAMENTOS\s+JUR[IÍ]DICOS\s+DEL\s+FALLO.*?)(POR\s+TANTO)",
        texto,
        re.DOTALL | re.IGNORECASE
    )
    ratio = patron_ratio.group(1).replace("III. FUNDAMENTOS JURÍDICOS DEL FALLO", "").strip() if patron_ratio else texto[:1500]

    return {
        "archivo": os.path.basename(ruta_pdf),
        "scp_numero": scp_numero,
        "sala": sala,
        "ratio_decidendi": ratio
    }

# =====================================================================
# 2. MOTOR RAG (BÚSQUEDA VECTORIAL)
# =====================================================================
class MotorRAG:
    def __init__(self, carpeta: str = "sentencias_pdf"):
        print("Cargando motor de búsqueda semántica...")
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.docs = []
        for arch in os.listdir(carpeta):
            if arch.endswith(".pdf"):
                self.docs.append(extraer_datos_pdf(os.path.join(carpeta, arch)))
        
        textos = [d["ratio_decidendi"] for d in self.docs]
        self.vectores = self.encoder.encode(textos)
        print(f"Biblioteca lista con {len(self.docs)} sentencias del TCP.\n")

    def buscar(self, consulta: str) -> dict:
        v_q = self.encoder.encode([consulta])
        sims = cosine_similarity(v_q, self.vectores)[0]
        idx = int(np.argmax(sims))
        res = self.docs[idx].copy()
        res["score"] = float(sims[idx])
        return res

# =====================================================================
# 3. AGENTE REDACTOR JURÍDICO (AUTO-DETECTA MODELO DISPONIBLE)
# =====================================================================
def redactar_dictamen_con_llm(hechos_caso: str, scp_datos: dict) -> str:
    print("Conectando con la IA y buscando modelo activo...")
    cliente_groq = Groq()

    try:
        lista_modelos = cliente_groq.models.list()
        # Filtramos explícitamente los "guardias" y modelos de audio
        modelos_validos = [m.id for m in lista_modelos.data if "guard" not in m.id.lower() and "whisper" not in m.id.lower()]
        
        print(f"Modelos disponibles en tu cuenta: {modelos_validos}")
        
        modelo_activo = modelos_validos[0]
        for m in modelos_validos:
            if "8b" in m.lower() or "70b" in m.lower() or "gemma" in m.lower() or "mixtral" in m.lower():
                modelo_activo = m
                break
        
        print(f"✅ Modelo redactor seleccionado: {modelo_activo}")
        print("Redactando el dictamen jurídico...\n")
    except Exception as e:
        return f"❌ Error de red con Groq al buscar modelos: {e}"

    prompt_sistema = """
Actúas como Abogado Senior y Socio Director de un prestigioso bufete en el Estado Plurinacional de Bolivia.
Tu tarea es redactar un DICTAMEN JURÍDICO PROFESIONAL fundado rigurosamente en la Constitución Política del Estado (CPE),
las leyes bolivianas pertinentes y el precedente vinculante del Tribunal Constitucional Plurinacional (TCP) provisto.

Estructura obligatoria de tu respuesta:
1. SÍNTESIS DE LOS HECHOS Y CALIFICACIÓN JURÍDICA
2. ANÁLISIS TÉCNICO-LEGAL (Leyes y Códigos de Bolivia aplicables)
3. SUBSUNCIÓN DEL PRECEDENTE DEL TCP (Cómo aplica la Ratio Decidendi al caso)
4. HOJA DE RUTA Y ESTRATEGIA PROCESAL (Paso a paso ante juzgados o Sala Constitucional)
5. EVALUACIÓN DE RIESGOS Y PLAZOS FATALES
"""

    prompt_usuario = f"""
DATOS DEL CASO REAL:
"{hechos_caso}"

DOCTRINA CONSTITUCIONAL VINCULANTE RECUPERADA POR EL RAG:
- Resolución: {scp_datos['scp_numero']} ({scp_datos['sala']})
- Ratio Decidendi: "{scp_datos['ratio_decidendi']}"

Redacta el Dictamen Jurídico formal para el cliente.
"""

    try:
        respuesta = cliente_groq.chat.completions.create(
            model=modelo_activo,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            temperature=0.2
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        return f"❌ ERROR DE GROQ AL REDACTAR: {str(e)}"

# =====================================================================
# 4. EJECUCIÓN DEL CASO
# =====================================================================
if __name__ == "__main__":
    motor = MotorRAG("sentencias_pdf")
    
    caso = (
        "Una trabajadora con 6 meses de embarazo fue despedida de la empresa Constructora del Sur "
        "sin que medie proceso ni causa justa. La Jefatura Departamental de Trabajo emitió la Conminatoria "
        "de Reincorporación formal, pero el empleador se niega a cumplirla y le impide el ingreso a su fuente laboral."
    )

    print("="*80)
    print("CASO DEL CLIENTE ENTRANTE:")
    print(f"\"{caso}\"")
    print("="*80)

    # 1. Recuperar la doctrina vinculante del PDF
    scp_encontrada = motor.buscar(caso)
    print(f"\n[RAG] Precedente encontrado: {scp_encontrada['scp_numero']} (Similitud: {scp_encontrada['score']:.4f})")

    # 2. El LLM genera el dictamen
    dictamen_completo = redactar_dictamen_con_llm(caso, scp_encontrada)

    print("\n" + "="*80)
    print("DICTAMEN JURÍDICO FORMAL EMITIDO POR EL BUFETE:")
    print("="*80)
    print(dictamen_completo)
    print("="*80)