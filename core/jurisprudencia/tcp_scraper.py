"""
Motor de Búsqueda y Scraping de Jurisprudencia del Tribunal Constitucional Plurinacional (TCP).
Permite consultar resoluciones en línea (Aletheia / tcpbolivia.bo) y buscar precedentes por materia y palabras clave.
"""
import re
import urllib.parse
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

from .corpus_data import CORPUS_JURISPRUDENCIA_BOLIVIA

class ScraperTCP:
    URL_BASE_BUSCADOR = "https://buscador.tcpbolivia.bo"
    URL_GACETA = "https://www.tcpbolivia.bo/tcp/gaceta"
    TIMEOUT = 6

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def buscar_en_linea(self, termino: str, materia: str = "", limite: int = 5) -> List[Dict[str, Any]]:
        """
        Intenta consultar el buscador oficial en línea del TCP o portales jurisprudenciales bolivianos.
        Si la conexión falla o el portal estatal está fuera de línea, realiza una búsqueda inteligente
        en el corpus local ampliado.
        """
        resultados: List[Dict[str, Any]] = []
        termino_limpio = termino.strip()

        # Intento 1: Scraping en línea
        try:
            params = {
                "q": termino_limpio,
                "materia": materia.lower()
            }
            url_consulta = f"{self.URL_BASE_BUSCADOR}/api/resoluciones?{urllib.parse.urlencode(params)}"
            resp = requests.get(url_consulta, headers=self.headers, timeout=self.TIMEOUT)
            
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data[:limite]:
                        resultados.append({
                            "origen": "TCP_ONLINE",
                            "scp_numero": item.get("numero", "SCP S/N"),
                            "sala": item.get("sala", "Sala Constitucional"),
                            "materia": materia or item.get("materia", "General"),
                            "tema": item.get("tema", termino_limpio),
                            "ratio_decidendi": item.get("ratio", item.get("resumen", "")),
                            "normas_clave": item.get("normas", [])
                        })
        except Exception:
            # Los servidores del Estado boliviano frecuentemente están offline o bloquean peticiones directas
            pass

        # Intento 2: Búsqueda en el corpus especializado integrado
        if not resultados:
            resultados = self.buscar_local(termino_limpio, materia=materia, limite=limite)

        return resultados

    def buscar_local(self, termino: str, materia: str = "", limite: int = 5) -> List[Dict[str, Any]]:
        """
        Búsqueda por coincidencia léxica, descriptores y palabras clave en el repositorio local verificado.
        """
        terminos = [t.lower() for t in re.findall(r"\w+", termino) if len(t) > 3]
        materia_filtro = materia.lower().strip() if materia else ""

        coincidencias = []
        for doc in CORPUS_JURISPRUDENCIA_BOLIVIA:
            # Filtro estricto de materia si se especifica
            if materia_filtro:
                doc_mat = doc.get("materia", "").lower()
                if materia_filtro not in doc_mat and doc_mat not in materia_filtro:
                    continue

            # Puntuación por coincidencia de términos
            score = 0
            texto_evaluable = f"{doc.get('tema', '')} {doc.get('ratio_decidendi', '')} {' '.join(doc.get('descriptores', []))}".lower()

            for t in terminos:
                if t in texto_evaluable:
                    score += 1
                for desc in doc.get("descriptores", []):
                    if t in desc.lower():
                        score += 2

            if score > 0 or not terminos:
                elem = doc.copy()
                elem["origen"] = "CORPUS_BOLIVIA"
                elem["score"] = score
                coincidencias.append(elem)

        # Ordenar por mayor coincidencia
        coincidencias.sort(key=lambda x: x.get("score", 0), reverse=True)
        return coincidencias[:limite]

    def obtener_sentencias_por_materia(self, materia: str) -> List[Dict[str, Any]]:
        """Devuelve todas las sentencias catalogadas bajo una materia específica."""
        mat_buscada = materia.lower().strip()
        return [
            doc for doc in CORPUS_JURISPRUDENCIA_BOLIVIA
            if mat_buscada in doc.get("materia", "").lower() or doc.get("materia", "").lower() in mat_buscada
        ]
