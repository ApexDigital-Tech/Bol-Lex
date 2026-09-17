import json
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# =====================================================================
# 1. BASE DE DATOS LOCAL: SENTENCIAS DEL TCP DE BOLIVIA (MINI-CORPUS)
# =====================================================================
CORPUS_TCP = [
    {
        "scp_numero": "SCP 0084/2017-S3",
        "materia": "Laboral",
        "tema": "Inamovilidad laboral de mujer embarazada y fuero de maternidad",
        "ratio_decidendi": "El fuero de maternidad y la inamovilidad laboral gozan de tutela directa e inmediata vía acción de amparo constitucional, prescindiendo del principio de subsidiariedad ante el incumplimiento de la conminatoria de reincorporación emitida por la Jefatura Departamental de Trabajo.",
        "normas_clave": ["Ley General del Trabajo", "CPE Art. 48", "D.S. 0012"]
    },
    {
        "scp_numero": "SCP 0011/2021-S2",
        "materia": "Penal",
        "tema": "Fundamentación y motivación en medidas cautelares de detención preventiva",
        "ratio_decidendi": "La imposición de la detención preventiva exige fundamentación clara y objetiva sobre los riesgos de fuga y obstaculización, debiendo los jueces evaluar de forma prioritaria medidas sustitutivas menos gravosas conforme a las modificaciones de la Ley 1173.",
        "normas_clave": ["Ley 1970", "Ley 1173", "Art. 233 CPP"]
    },
    {
        "scp_numero": "SCP 0256/2018-S2",
        "materia": "Familia",
        "tema": "Apremio corporal por asistencia familiar e interés superior del menor",
        "ratio_decidendi": "El mandamiento de apremio por incumplimiento de asistencia familiar aprobada judicialmente es una medida excepcional de coerción constitucionalmente válida orientada a garantizar los derechos primordiales de subsistencia de los hijos.",
        "normas_clave": ["Ley 603", "Código de las Familias", "Art. 127 Ley 603"]
    }
]

# =====================================================================
# 2. MOTOR DE BÚSQUEDA VECTORIAL (RAG LOCAL)
# =====================================================================
class MotorRAGJurisprudencial:
    def __init__(self):
        print("Cargando modelo local de embeddings (esto toma unos segundos)...")
        # Modelo multilingüe optimizado para español, rápido y liviano
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.corpus = CORPUS_TCP
        
        # Generar vectores de las sentencias almacenadas
        textos_a_indexar = [f"{doc['tema']} {doc['ratio_decidendi']}" for doc in self.corpus]
        self.vectores_corpus = self.encoder.encode(textos_a_indexar)
        print("Biblioteca del TCP indexada y lista.")

    def buscar_precedente(self, consulta: str, top_k: int = 1) -> List[Dict[str, Any]]:
        vector_consulta = self.encoder.encode([consulta])
        similitudes = cosine_similarity(vector_consulta, self.vectores_corpus)[0]
        
        # Ordenar de mayor a menor similitud
        mejores_indices = np.argsort(similitudes)[::-1][:top_k]
        
        resultados = []
        for idx in mejores_indices:
            res = self.corpus[idx].copy()
            res["similitud_score"] = float(similitudes[idx])
            resultados.append(res)
        return resultados

# =====================================================================
# 3. LOS AGENTES JURÍDICOS (DIRECTOR + ESPECIALISTAS)
# =====================================================================
class AgenteDirector:
    """Clasifica el caso y enruta al especialista competente."""
    def clasificar(self, hechos: str) -> str:
        hechos_lower = hechos.lower()
        if any(w in hechos_lower for w in ["despido", "embaraz", "reincorporaci", "sueldo", "laboral"]):
            return "Laboral"
        elif any(w in hechos_lower for w in ["cautelar", "detención preventiva", "cárcel", "delito", "imputac"]):
            return "Penal"
        elif any(w in hechos_lower for w in ["asistencia familiar", "pensión", "apremio", "hijo", "divorcio"]):
            return "Familia"
        return "Constitucional"

class BufeteDigital:
    def __init__(self):
        self.director = AgenteDirector()
        self.rag = MotorRAGJurisprudencial()

    def resolver_caso(self, hechos: str) -> Dict[str, Any]:
        # 1. Mesa de entrada: El Director evalúa competencia
        materia = self.director.clasificar(hechos)
        
        # 2. El pasante del archivo: Búsqueda vectorial de la jurisprudencia
        precedentes = self.rag.buscar_precedente(hechos, top_k=1)
        mejor_precedente = precedentes[0]

        # 3. Especialista: Elaboración del dictamen
        dictamen = {
            "materia_asignada": materia,
            "precedente_tcp": mejor_precedente["scp_numero"],
            "score_relevancia": round(mejor_precedente["similitud_score"], 4),
            "ratio_aplicada": mejor_precedente["ratio_decidendi"],
            "normas_aplicables": mejor_precedente["normas_clave"],
            "estrategia_sugerida": self._determinar_estrategia(materia, mejor_precedente)
        }
        return dictamen

    def _determinar_estrategia(self, materia: str, precedente: Dict[str, Any]) -> str:
        if materia == "Laboral":
            return "Presentar Acción de Amparo Constitucional de forma inmediata invocando la conminatoria y la SCP citada sin esperar juicios laborales ordinarios."
        elif materia == "Penal":
            return "Interponer recurso de Apelación Incidental dentro de las 72 horas conforme a la Ley 1173 acreditando falta de fundamentación objetiva de riesgos procesales."
        elif materia == "Familia":
            return "Solicitar al Juez Público de Familia la expedición de Mandamiento de Apremio Corporal conforme al Art. 127 de la Ley 603."
        return "Demanda por la vía ordinaria."

# =====================================================================
# 4. SUITE DE EVALUACIÓN TÉCNICA-JURÍDICA (EL EXAMEN DE GRADO)
# =====================================================================
def ejecutar_suite_evaluacion():
    print("\n" + "="*70)
    print("INICIANDO SUITE DE EVALUACIÓN TÉCNICA-JURÍDICA (BENCHMARK BOLIVIA)")
    print("="*70)

    # El Ground Truth (Hoja de examen con respuestas correctas)
    casos_de_prueba = [
        {
            "id": "CASO-01",
            "hechos": "Una trabajadora con 5 meses de embarazo fue despedida de su empresa. La Jefatura de Trabajo ordenó su reincorporación pero el empleador no le permite entrar.",
            "materia_esperada": "Laboral",
            "scp_esperada": "SCP 0084/2017-S3",
            "norma_esperada": "Ley General del Trabajo"
        },
        {
            "id": "CASO-02",
            "hechos": "El juez cautelar mandó a mi cliente a la cárcel con detención preventiva sin fundamentar por qué no procedía una fianza o arraigo domiciliario.",
            "materia_esperada": "Penal",
            "scp_esperada": "SCP 0011/2021-S2",
            "norma_esperada": "Ley 1173"
        },
        {
            "id": "CASO-03",
            "hechos": "El demandado no cancela las pensiones de sus dos hijos desde hace 7 meses. La liquidación ya fue aprobada por el juez y pedimos su captura.",
            "materia_esperada": "Familia",
            "scp_esperada": "SCP 0256/2018-S2",
            "norma_esperada": "Ley 603"
        }
    ]

    bufete = BufeteDigital()
    aciertos_materia = 0
    aciertos_jurisprudencia = 0
    total = len(casos_de_prueba)

    for caso in casos_de_prueba:
        print(f"\nProbando [{caso['id']}]...")
        resultado = bufete.resolver_caso(caso["hechos"])

        # Control 1: Clasificación de materia
        ok_materia = resultado["materia_asignada"] == caso["materia_esperada"]
        if ok_materia: aciertos_materia += 1

        # Control 2: Recuperación de la SCP correcta
        ok_scp = resultado["precedente_tcp"] == caso["scp_esperada"]
        if ok_scp: aciertos_jurisprudencia += 1

        print(f" -> Materia detectada: {resultado['materia_asignada']} [{'OK' if ok_materia else 'FALLO'}]")
        print(f" -> Precedente TCP:    {resultado['precedente_tcp']} (Score: {resultado['score_relevancia']}) [{'OK' if ok_scp else 'FALLO'}]")
        print(f" -> Estrategia:        {resultado['estrategia_sugerida']}")

    # Cálculo de métricas
    tasa_materia = (aciertos_materia / total) * 100
    tasa_rag = (aciertos_jurisprudencia / total) * 100
    nota_final = (tasa_materia + tasa_rag) / 2

    print("\n" + "="*70)
    print("RESULTADOS DE LA AUDITORÍA JURÍDICA")
    print("="*70)
    print(f"1. Precisión de Enrutamiento (Director):   {tasa_materia:.1f}%")
    print(f"2. Precisión de Búsqueda Vectorial (RAG):  {tasa_rag:.1f}%")
    print(f"NOTA FINAL DEL SISTEMA:                     {nota_final:.1f}/100")
    print("="*70)

if __name__ == "__main__":
    ejecutar_suite_evaluacion()