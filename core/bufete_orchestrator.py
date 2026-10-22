"""
Orquestador Principal del Sistema Multi-Agente (Bol-Lex AI).
Coordina el flujo de trabajo de los agentes especialistas bajo programación defensiva y trazabilidad.
"""
import os
import json
from typing import Dict, Any, List, Tuple
from datetime import datetime

from .llm_client import MotorLLM
from .extractor import ExtractorDocumental
from .jurisprudencia import MotorRAGJurisprudencial, ScraperTCP
from .agents import (
    AgenteDirector, 
    AgenteAuditorEvidencia, 
    AgenteEspecialistaSenior, 
    AgenteRedactorForense
)

class OrquestadorBufete:
    def __init__(self, api_key: str = ""):
        self.motor_llm = MotorLLM(api_key=api_key)
        self.extractor = ExtractorDocumental()
        self.rag = MotorRAGJurisprudencial()
        self.scraper = ScraperTCP()

        # Instanciar el equipo de agentes especialistas
        self.director = AgenteDirector(self.motor_llm)
        self.auditor = AgenteAuditorEvidencia(self.motor_llm)
        self.especialista = AgenteEspecialistaSenior(self.motor_llm)
        self.redactor = AgenteRedactorForense(self.motor_llm)

    def ejecutar_flujo_completo(
        self,
        titulo_caso: str,
        instrucciones_caso: str,
        carpeta_caso: str,
        materia_preferida: str = ""
    ) -> Dict[str, Any]:
        """
        Ejecuta el ciclo agéntico completo:
        1. Triaje y Calificación (Director)
        2. Extracción y Auditoría Forense (Auditor Evidencias)
        3. Localización de Precedentes Reales TCP (Investigador RAG)
        4. Dictamen Estratégico (Especialista Senior)
        """
        logs_proceso: List[str] = []
        os.makedirs(carpeta_caso, exist_ok=True)

        # -------------------------------------------------------------
        # PASO 1: Listar archivos físicos en el expediente
        # -------------------------------------------------------------
        archivos_disco = [
            a for a in os.listdir(carpeta_caso)
            if a.endswith((".pdf", ".txt", ".docx"))
            and not a.startswith(("Dictamen_", "Memorial_"))
            and not a.endswith((".cache.txt", ".ocr_cache.txt", ".ficha_auditada.json", "meta.json"))
        ]
        logs_proceso.append(f"📁 [EXPEDIENTE] {len(archivos_disco)} piezas probatorias localizadas.")

        # -------------------------------------------------------------
        # PASO 2: Agente Director (Triaje y Calificación)
        # -------------------------------------------------------------
        logs_proceso.append("👔 [AGENTE DIRECTOR] Analizando pretensión y competencia...")
        analisis_director = self.director.analizar_caso(instrucciones_caso, archivos_disco)
        
        materia_final = materia_preferida if materia_preferida else analisis_director.get("materia_principal", "Civil")
        logs_proceso.append(f"⚖️ [MATERIA ASIGNADA] {materia_final} | Vía: {analisis_director.get('via_procesal_recomendada', 'Vía Ordinaria')}")

        # -------------------------------------------------------------
        # PASO 3: Extracción Documental Certificada & Auditoría Forense
        # -------------------------------------------------------------
        logs_proceso.append("🔍 [AGENTE AUDITOR] Inspeccionando documentos y extrayendo hechos constatables...")
        fichas_auditadas: List[Dict[str, Any]] = []

        for arch in archivos_disco:
            ruta_completa = os.path.join(carpeta_caso, arch)
            texto, diag = self.extractor.extraer_texto(ruta_completa, arch, carpeta_caso=carpeta_caso)
            ficha = self.auditor.auditar_documento_individual(arch, texto, carpeta_caso=carpeta_caso, diagnostico=diag)
            fichas_auditadas.append(ficha)
            estado_lectura = "OK" if diag.get("legible") else "ILEGIBLE"
            logs_proceso.append(f"  • {arch}: {diag.get('metodo', 'digital')} ({diag.get('caracteres', 0)} caracteres) [{estado_lectura}]")

        informe_evidencias = self.auditor.consolidar_expediente(fichas_auditadas)

        # -------------------------------------------------------------
        # PASO 4: Investigador Jurisprudencial (TCP RAG con Aislamiento)
        # -------------------------------------------------------------
        logs_proceso.append(f"📚 [INVESTIGADOR TCP] Buscando precedentes vinculantes en materia {materia_final}...")
        precedente_tcp = self.rag.buscar_precedente_pertinente(instrucciones_caso, materia_caso=materia_final)
        logs_proceso.append(f"🏛️ [FALLO TCP RECUPERADO] {precedente_tcp.get('scp_numero', 'S/N')} ({precedente_tcp.get('sala', '')})")

        # -------------------------------------------------------------
        # PASO 5: Agente Especialista Senior (Emisión del Dictamen)
        # -------------------------------------------------------------
        logs_proceso.append("✍️ [ESPECIALISTA SENIOR] Redactando Dictamen Jurídico y Diagnóstico...")
        dictamen_texto = self.especialista.emitir_dictamen(
            titulo_caso=titulo_caso,
            materia=materia_final,
            instrucciones_cliente=instrucciones_caso,
            informe_auditoria_evidencia=informe_evidencias,
            precedente_tcp=precedente_tcp
        )

        # -------------------------------------------------------------
        # PASO 6: Compilación de Archivos Finales (.md y .pdf)
        # -------------------------------------------------------------
        cod_caso = os.path.basename(carpeta_caso)
        ruta_md = os.path.join(carpeta_caso, f"Dictamen_{cod_caso}.md")
        with open(ruta_md, "w", encoding="utf-8") as f:
            f.write(dictamen_texto)

        ruta_pdf = os.path.join(carpeta_caso, f"Dictamen_{cod_caso}.pdf")
        self.redactor.exportar_pdf(dictamen_texto, ruta_pdf)
        logs_proceso.append("✅ [COMPILACIÓN] Dictamen generado en Markdown y PDF formal.")

        return {
            "titulo": titulo_caso,
            "materia": materia_final,
            "director": analisis_director,
            "evidencias_auditadas": informe_evidencias,
            "fichas": fichas_auditadas,
            "precedente_tcp": precedente_tcp,
            "dictamen": dictamen_texto,
            "ruta_pdf": ruta_pdf,
            "ruta_md": ruta_md,
            "logs": logs_proceso
        }

    def generar_memorial(
        self,
        titulo_caso: str,
        materia: str,
        suma: str,
        abogado: str,
        carpeta_caso: str,
        instrucciones_extra: str = ""
    ) -> Tuple[str, str, str]:
        """
        Genera el memorial forense y devuelve (texto_memorial, ruta_docx, ruta_pdf).
        """
        cod_caso = os.path.basename(carpeta_caso)
        
        # Recuperar informe de auditoría si ya existe
        fichas_auditadas = []
        for arch in os.listdir(carpeta_caso):
            if arch.endswith(".ficha_auditada.json"):
                try:
                    with open(os.path.join(carpeta_caso, arch), "r", encoding="utf-8") as f:
                        fichas_auditadas.append(json.load(f))
                except Exception:
                    pass
        
        evidencias = self.auditor.consolidar_expediente(fichas_auditadas) if fichas_auditadas else "Conforme a los antecedentes documentales en obrados."

        mem_texto = self.redactor.redactar_memorial(
            titulo_caso=titulo_caso,
            materia=materia,
            suma_pretendida=suma,
            abogado_firmante=abogado,
            evidencia_auditada=evidencias,
            instrucciones_especificas=instrucciones_extra
        )

        ruta_docx = os.path.join(carpeta_caso, f"Memorial_{cod_caso}.docx")
        self.redactor.exportar_docx(mem_texto, ruta_docx)

        ruta_pdf = os.path.join(carpeta_caso, f"Memorial_{cod_caso}.pdf")
        self.redactor.exportar_pdf(mem_texto, ruta_pdf)

        return mem_texto, ruta_docx, ruta_pdf
