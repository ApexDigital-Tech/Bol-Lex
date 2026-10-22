"""
Módulo de Jurisprudencia del Estado Plurinacional de Bolivia.
Incluye corpus multimateria verificado, scraper de sentencias del TCP y motor RAG blindado.
"""
from .corpus_data import CORPUS_JURISPRUDENCIA_BOLIVIA
from .tcp_scraper import ScraperTCP
from .rag_engine import MotorRAGJurisprudencial

__all__ = ["CORPUS_JURISPRUDENCIA_BOLIVIA", "ScraperTCP", "MotorRAGJurisprudencial"]
