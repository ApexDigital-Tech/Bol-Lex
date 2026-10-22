"""
Motor RAG Especializado con Filtro de Aislamiento de Materia (Zero-Contamination).
Impide terminantemente la inyección de precedentes de ramas ajenas a la controversia.
"""
from typing import Dict, Any, List, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .corpus_data import CORPUS_JURISPRUDENCIA_BOLIVIA
from .tcp_scraper import ScraperTCP

class MotorRAGJurisprudencial:
    def __init__(self):
        self.corpus = CORPUS_JURISPRUDENCIA_BOLIVIA
        self.scraper = ScraperTCP()

    def buscar_precedente_pertinente(self, hechos_o_consulta: str, materia_caso: str) -> Dict[str, Any]:
        """
        Recupera el precedente vinculante más adecuado bajo aislamiento estricto de materia.
        Si la materia es Civil o Contratos, NUNCA retornará una sentencia laboral ni penal.
        """
        materia_normalizada = materia_caso.strip().lower()

        # 1. Filtrar corpus exclusivamente para la materia en controversia
        docs_materia = [
            d for d in self.corpus
            if materia_normalizada in d["materia"].lower() 
            or d["materia"].lower() in materia_normalizada
            # También permitir Constitucional general si se analiza vía tutelar
            or ("constitucional" in materia_normalizada and d["materia"] == "Constitucional")
        ]

        # Si no hay sentencias registradas para esa materia exacta, intentar scraper en línea
        if not docs_materia:
            online_results = self.scraper.buscar_en_linea(hechos_o_consulta, materia=materia_caso, limite=1)
            if online_results:
                return online_results[0]
            
            # Blindaje anti-alucinación: declarar expresamente la ausencia de precedente específico
            return {
                "scp_numero": "Sin precedente jurisprudencial específico registrado",
                "sala": "-",
                "materia": materia_caso,
                "tema": "Fundamentación legal directa",
                "ratio_decidendi": "No se forzará la aplicación de precedentes de otras ramas. El caso debe fundarse directamente en las normas positivas aplicables (leyes y códigos sustantivos y adjetivos vigentes en Bolivia).",
                "normas_clave": []
            }

        # 2. Búsqueda vectorial semántica TF-IDF (100% local, n-gramas, cero latencia de red)
        try:
            textos_filtrados = [
                f"{d['materia']} {d['tema']} {d['ratio_decidendi']} {' '.join(d.get('normas_clave', []))} {' '.join(d.get('descriptores', []))}" 
                for d in docs_materia
            ]
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
            tfidf_mat = vectorizer.fit_transform(textos_filtrados)
            v_q = vectorizer.transform([hechos_o_consulta])
            sims = cosine_similarity(v_q, tfidf_mat)[0]
            if np.max(sims) > 0.02:
                idx_mejor = int(np.argmax(sims))
                res = docs_materia[idx_mejor].copy()
                res["similitud_score"] = float(sims[idx_mejor])
                return res
        except Exception:
            pass

        # 3. Fallback léxico dentro de la materia filtrada
        coincidencias = self.scraper.buscar_local(hechos_o_consulta, materia=materia_caso, limite=1)
        if coincidencias:
            return coincidencias[0]

        return docs_materia[0]
