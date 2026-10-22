"""
Agente 3: Abogado Senior Consultor Especialista por Materia.
Elabora el Dictamen Jurídico y Diagnóstico Estratégico de Fondo fundamentado en la ley boliviana.
"""
from typing import Dict, Any
from ..llm_client import MotorLLM

PROMPTS_ESPECIALISTAS_MATERIA = {
    "Civil": """
Actúas como Consultor Jurídico Senior Especialista en Derecho Civil, Comercial y Contrataciones del Estado en Bolivia (Ley 1178 SAFCO, Ley 439 CPC, Código Civil y D.S. 0181).
Tu objetivo es formular una estrategia legal agresiva y procesalmente viable para la recuperación patrimonial o defensa de derechos del cliente.
Analiza la exigibilidad de contratos bilaterales, adendas, actas de entrega/recepción definitiva, cartas notariales de requerimiento de mora y títulos ejecutivos.
""",
    "Contrataciones Estatales": """
Actúas como Abogado Senior Especialista en Contrataciones Administrativas del Estado Boliviano (D.S. 0181 NB-SABS y Ley 1178).
Tu foco es la exigibilidad de planillas de avance, liquidación final de obras/servicios, retenciones indebidas y responsabilidad contractual de entidades públicas (EBC, Ministerios, Gobiernos Autónomos).
""",
    "Constitucional": """
Actúas como Abogado Constitucionalista Senior en Bolivia (CPE y Código Procesal Constitucional Ley 254).
Analizas rigurosamente los presupuestos de admisibilidad de la Acción de Amparo Constitucional: Principio de Inmediatez (plazo fatal de 6 meses), Principio de Subsidiariedad (agotamiento de vías ordinarias o acreditación de vías de hecho/daño irreparable).
""",
    "Laboral": """
Actúas como Abogado Laboralista Senior en Bolivia (Ley General del Trabajo, D.S. 28699, D.S. 0495 y Código Procesal del Trabajo).
Analizas derechos laborales adquiridos, conminatorias de reincorporación de cumplimiento obligatorio, finiquitos y beneficios sociales.
""",
    "Penal": """
Actúas como Abogado Penalista Senior bajo el sistema procesal boliviano (Ley 1970 y Ley 1173).
Evalúas tipicidad, exclusión de la vía penal para meras deudas civiles, medidas cautelares y salidas alternativas.
"""
}

class AgenteEspecialistaSenior:
    def __init__(self, motor_llm: MotorLLM):
        self.llm = motor_llm

    def emitir_dictamen(
        self, 
        titulo_caso: str,
        materia: str,
        instrucciones_cliente: str, 
        informe_auditoria_evidencia: str,
        precedente_tcp: Dict[str, Any]
    ) -> str:
        """
        Emite el Dictamen Jurídico y Diagnóstico Estratégico con máxima pulcritud técnica.
        """
        prompt_rol = PROMPTS_ESPECIALISTAS_MATERIA.get(materia, PROMPTS_ESPECIALISTAS_MATERIA["Civil"])
        
        prompt_sistema = f"""
{prompt_rol}

ESTRUCTURA OBLIGATORIA DEL DICTAMEN:
# DICTAMEN JURÍDICO Y ESTRATEGIA LITIGIOSA: {titulo_caso.upper()}

## 1. CALIFICACIÓN JURÍDICA Y PARTES PROCESALES
- Identificación de Sujetos: Acreedor/Recurrente vs. Deudor/Entidad recurrida con sus personerías acreditadas en la evidencia.
- Naturaleza del Vínculo: Relación contractual, administrativa o tutelar.

## 2. ANTECEDENTES FÁCTICOS PROBADOS EN OBRADOS
- Cronología estricta de documentos constatados por la auditoría forense (Contratos, adendas, notas y actas de recepción).
- Obligación económica verificable (montos pactados, pagos certificados y saldo insoluto exigible).

## 3. DOCTRINA Y PRECEDENTES DEL TRIBUNAL CONSTITUCIONAL PLURINACIONAL (TCP)
- Subsunción de la Ratio Decidendi de la resolución constitucional vinculante al caso concreto.
- Citas de normas sustantivas y adjetivas bolivianas aplicables.

## 4. VIABILIDAD PROCESAL Y ANÁLISIS DE VÍAS IDÓNEAS
- Vía Ejecutiva / Monitoria (Ley 439): Presupuestos de ejecutabilidad y embargo preventivo.
- Vía Constitucional (Amparo): ¿Procede o rige el principio de subsidiariedad?
- Vía Contenciosa / Administrativa (Ley 1178 y Ley 2341): Reclamación ante la Máxima Autoridad Ejecutiva (MAE).

## 5. PLAN DE ACCIÓN OPERATIVO Y PLAZOS FATALES
- Cronograma de requerimientos notariales con plazo conminatorio.
- Medidas cautelares a solicitar (retención judicial de cuentas bancarias y bienes del deudor).
- Plazos de prescripción e inmediatez.

REGLA ANTI-ALUCINACIÓN:
- Basa tus conclusiones ÚNICAMENTE en la evidencia probada provista.
- Si una prueba no existe en la auditoría, indícala expresamente como 'Elemento pendiente de subsanar por el cliente'.
"""

        precedente_texto = f"""
FALLO VINCULANTE SELECCIONADO:
- Resolución: {precedente_tcp.get('scp_numero', 'Sin fallo asignado')} ({precedente_tcp.get('sala', '')})
- Tema: {precedente_tcp.get('tema', 'Doctrina general')}
- Ratio Decidendi: "{precedente_tcp.get('ratio_decidendi', 'Aplicación de norma legal positiva')}"
- Normas clave: {', '.join(precedente_tcp.get('normas_clave', []))}
"""

        prompt_usuario = f"""
INSTRUCCIONES Y REQUERIMIENTO DEL CLIENTE:
{instrucciones_cliente}

{precedente_texto}

INFORME FORENSE DE DOCUMENTOS Y HECHOS ACREDITADOS:
{informe_auditoria_evidencia[:7500]}
"""
        return self.llm.invocar(
            mensajes=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            temperatura=0.05,
            max_tokens=3200,
            auto_continuar=True
        )
