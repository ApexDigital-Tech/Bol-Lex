"""
Paquete de Agentes Jurídicos Especializados Senior (Bol-Lex AI).
"""
from .director import AgenteDirector
from .evidence_auditor import AgenteAuditorEvidencia
from .specialist import AgenteEspecialistaSenior
from .forensic_writer import AgenteRedactorForense

__all__ = [
    "AgenteDirector",
    "AgenteAuditorEvidencia",
    "AgenteEspecialistaSenior",
    "AgenteRedactorForense"
]
