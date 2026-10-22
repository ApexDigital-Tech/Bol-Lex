"""
Agente 1: Director de Triaje y Estrategia Jurídica Senior.
Analiza la pretensión del cliente, califica los hechos y determina la materia procesal exacta.
"""
import json
from typing import Dict, Any, List
from ..llm_client import MotorLLM

class AgenteDirector:
    def __init__(self, motor_llm: MotorLLM):
        self.llm = motor_llm

    def analizar_caso(self, hechos_cliente: str, archivos_nombres: List[str]) -> Dict[str, Any]:
        """
        Determina la calificación jurídica del caso, partes procesales y la materia principal.
        """
        prompt_sistema = """
Actúas como Socio Director General de un prestigioso bufete jurídico en Bolivia.
Tu función es clasificar con máxima precisión técnica el caso presentado por el cliente.

MATERIAS VÁLIDAS:
- "Civil" (Contratos bilaterales, cobro de deudas, procesos ejecutivos, monitorios, títulos ejecutivos)
- "Contrataciones Estatales" (Contratos con empresas públicas como EBC, YPFB, Ministerios, DS 0181, Ley 1178)
- "Constitucional" (Acciones de Amparo contra vías de hecho o actos manifiestamente arbitrarios)
- "Laboral" (Beneficios sociales, conminatorias del Ministerio de Trabajo, despidos)
- "Penal" (Delitos tipificados en el Código Penal, medidas cautelares)
- "Familia" (Asistencia familiar, divorcios, Ley 603)
- "Administrativo" (Impugnaciones, Ley 2341)

Devuelve tu análisis estrictamente en formato JSON con esta estructura exacta:
{
  "materia_principal": "Civil" o la correspondiente,
  "submateria": "Cobro de deuda en contrato de obra" o similar,
  "via_procesal_recomendada": "Vía Ejecutiva / Monitoria" o "Acción de Amparo Constitucional" o "Vía Ordinaria",
  "parte_activa": "Nombre o identificación preliminar del acreedor/recurrente",
  "parte_pasiva": "Nombre o identificación preliminar del deudor/recurrido (ej: EBC)",
  "pretension_central": "Resumen en una frase del objetivo económico o tutelar pretendido",
  "instruccion_auditoria": "Puntos clave que el Auditor de Evidencia debe buscar obligatoriamente"
}
"""
        archivos_str = ", ".join(archivos_nombres) if archivos_nombres else "Sin archivos adjuntos iniciales."
        prompt_usuario = f"""
HECHOS / INSTRUCCIÓN DEL CLIENTE:
"{hechos_cliente}"

DOCUMENTOS ADJUNTOS EN EXPEDIENTE:
{archivos_str}
"""
        try:
            raw_json = self.llm.invocar(
                mensajes=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario}
                ],
                temperatura=0.0,
                max_tokens=1000,
                json_mode=True
            )
            return json.loads(raw_json)
        except Exception:
            # Fallback defensivo ante fallos de formato JSON
            materia = "Civil"
            hc = hechos_cliente.lower()
            if "ebc" in hc or "contrato" in hc or "deuda" in hc or "planilla" in hc:
                materia = "Civil"
            elif "amparo" in hc or "constitucional" in hc:
                materia = "Constitucional"
            elif "trabajo" in hc or "laboral" in hc:
                materia = "Laboral"
            elif "penal" in hc or "delito" in hc:
                materia = "Penal"

            return {
                "materia_principal": materia,
                "submateria": "Controversia patrimonial o contractual",
                "via_procesal_recomendada": "Vía Ejecutiva o Coactiva",
                "parte_activa": "Acreedor / Demandante",
                "parte_pasiva": "Deudor / Entidad Contratante",
                "pretension_central": hechos_cliente[:120],
                "instruccion_auditoria": "Verificar montos, actas de recepción definitiva y cartas notariales de requerimiento de pago."
            }
