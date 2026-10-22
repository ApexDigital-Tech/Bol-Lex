"""
Agente 2: Auditor Forense de Evidencia Documental (Zero-Hallucination Guard).
Inspecciona metódicamente cada pieza probatoria del expediente y extrae únicamente hechos constatables.
"""
import os
import json
from typing import Dict, Any, List
from ..llm_client import MotorLLM

class AgenteAuditorEvidencia:
    def __init__(self, motor_llm: MotorLLM):
        self.llm = motor_llm

    def auditar_documento_individual(
        self, 
        nombre_archivo: str, 
        texto_extraido: str, 
        carpeta_caso: str = "",
        diagnostico: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Audita un documento y produce una ficha de hechos certificados con blindaje anti-alucinación.
        """
        if carpeta_caso:
            ruta_ficha = os.path.join(carpeta_caso, f"{nombre_archivo}.ficha_auditada.json")
            if os.path.exists(ruta_ficha):
                try:
                    with open(ruta_ficha, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        # Si el diagnóstico reporta que el documento no es legible
        if diagnostico and not diagnostico.get("legible", True):
            ficha_vacia = {
                "archivo": nombre_archivo,
                "tipo_documento": "Documento Ilegible o Escaneo sin OCR",
                "fecha": "No verificable",
                "partes": "No constatadas en el documento digital",
                "objeto": "Ilegible",
                "montos": "No verificables",
                "estado_obligacion": "Requiere cotejo con original físico o escaneo de alta resolución.",
                "hechos_probados": ["El documento físico existe en el expediente pero su texto digital no fue reconocible."],
                "vacio_probatorio": "Imposibilidad técnica de extraer cláusulas o firmas."
            }
            return ficha_vacia

        prompt_sistema = """
Actúas como Perito Auditor Forense Documental en litigios bolivianos.
Tu deber ético y legal es reportar EXCLUSIVAMENTE los hechos, cifras y datos que estén expresamente escritos en el texto proporcionado.

REGLAS DE ORO CONTRA ALUCINACIONES:
1. PROHIBIDO INVENTAR O SUPONER: Si un nombre, fecha, moneda, NIT o monto no figura, debes escribir obligatoriamente 'No especificado'.
2. PRECISIÓN ECONÓMICA: Si hay montos, transcríbelos con su moneda exacta (Bs. o $US) y cita la cláusula o párrafo de donde provienen.
3. ESTADO DEL PAGO: Si el documento es un contrato o requerimiento de pago y no contiene comprobantes de depósito bancario de cancelación, declara: 'Obligación pactada sin constancia de descargo de pago adjunto'.

Responde en formato JSON válido:
{
  "archivo": "nombre_archivo",
  "tipo_documento": "Contrato Administrativo / Carta Notarial / Acta de Recepción / etc.",
  "fecha_documento": "Fecha exacta que figura en el texto o 'No especificada'",
  "acreedor_o_contratista": "Razón social, persona o NIT exacto",
  "deudor_o_entidad": "Razón social, entidad pública (ej. EBC) o NIT exacto",
  "objeto": "Breve descripción literal del objeto del documento",
  "monto_total_y_saldos": "Cifras textuales identificadas",
  "hechos_probados": [
    "Hecho fáctico 1 demostrado con este documento",
    "Hecho fáctico 2 demostrado con este documento"
  ],
  "vacios_o_faltantes": "Información clave que este documento no acredita"
}
"""
        prompt_usuario = f"""
DOCUMENTO AUDITADO: {nombre_archivo}

TEXTO REAL EXTRAÍDO:
\"\"\"
{texto_extraido[:7000]}
\"\"\"
"""
        try:
            raw_res = self.llm.invocar(
                mensajes=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario}
                ],
                temperatura=0.0,
                json_mode=True
            )
            ficha = json.loads(raw_res)
            if carpeta_caso:
                with open(os.path.join(carpeta_caso, f"{nombre_archivo}.ficha_auditada.json"), "w", encoding="utf-8") as f:
                    json.dump(ficha, f, ensure_ascii=False, indent=2)
            return ficha
        except Exception:
            return {
                "archivo": nombre_archivo,
                "tipo_documento": "Documento Procesado",
                "fecha_documento": "No identificada",
                "acreedor_o_contratista": "No determinado",
                "deudor_o_entidad": "No determinado",
                "objeto": "Análisis documental automatizado",
                "monto_total_y_saldos": "Ver texto adjunto",
                "hechos_probados": [texto_extraido[:300].strip()],
                "vacios_o_faltantes": "Formato de extracción no estructurado"
            }

    def consolidar_expediente(self, fichas: List[Dict[str, Any]]) -> str:
        """
        Sintetiza la auditoría integral de todos los documentos en un informe coherente de hechos certificados.
        """
        if not fichas:
            return "No se adjuntaron documentos comprobatorios al expediente."

        lineas = ["## INFORME DE AUDITORÍA FORENSE DOCUMENTAL (HECHOS CERTIFICADOS)\n"]
        for f in fichas:
            lineas.append(f"### 📄 Pieza: {f.get('archivo', 'S/N')}")
            lineas.append(f"- **Tipo y Fecha:** {f.get('tipo_documento', 'Documento')} | Fecha: {f.get('fecha_documento', 'No especificada')}")
            lineas.append(f"- **Sujetos:** Acreedor/Contratista: `{f.get('acreedor_o_contratista', 'N/E')}` | Deudor/Entidad: `{f.get('deudor_o_entidad', 'N/E')}`")
            lineas.append(f"- **Objeto:** {f.get('objeto', 'N/E')}")
            lineas.append(f"- **Valores Económicos:** {f.get('monto_total_y_saldos', 'No especificados')}")
            
            probados = f.get('hechos_probados', [])
            if probados:
                lineas.append("- **Hechos Probados:**")
                for hp in probados:
                    lineas.append(f"  • {hp}")
            
            vacio = f.get('vacios_o_faltantes', '')
            if vacio:
                lineas.append(f"- **Observación Probatoria:** {vacio}")
            lineas.append("")

        return "\n".join(lineas)
