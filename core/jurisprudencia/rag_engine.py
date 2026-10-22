"""
Motor RAG Especializado con Filtro de Aislamiento de Materia (Zero-Contamination).
Impide terminantemente la inyección de precedentes de ramas ajenas a la controversia.
"""
from typing import Dict, Any, List, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .corpus_data import CORPUS_JURISPRUDENCIA_BOLIVIA
from .tcp_scraper import ScraperTCP

class MotorRAGJurisprudencial:
    def __init__(self):
        self.corpus = CORPUS_JURISPRUDENCIA_BOLIVIA
        self.scraper = ScraperTCP()
        self.encoder = None
        self.vectores_corpus = None
        self._inicializar_encoder()

    def _inicializar_encoder(self):
        """Carga perezosa del modelo de embeddings."""
        try:
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            textos = [f"{d['materia']} {d['tema']} {d['ratio_decidendi']}" for d in self.corpus]
            self.vectores_corpus = self.encoder.encode(textos)
        except Exception:
            self.encoder = None
            self.vectores_corpus = None

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

        # 2. Búsqueda semántica dentro del subconjunto de la materia
        if self.encoder is not None:
            try:
                v_q = self.encoder.encode([hechos_o_consulta])
                textos_filtrados = [f"{d['tema']} {d['ratio_decidendi']}" for d in docs_materia]
                vectores_filtrados = self.encoder.encode(textos_filtrados)
                sims = cosine_similarity(v_q, vectores_filtrados)[0]
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
