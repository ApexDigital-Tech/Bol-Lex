"""
Base de Datos Jurisprudencial Boliviana (Corpus Multimateria Verificado).
Contiene fallos vinculantes del Tribunal Constitucional Plurinacional (TCP) y Tribunal Supremo de Justicia (TSJ).
"""
from typing import List, Dict, Any

CORPUS_JURISPRUDENCIA_BOLIVIA: List[Dict[str, Any]] = [
    # =====================================================================
    # MATERIA: CIVIL Y CONTRATACIONES DEL ESTADO / COBRO DE DEUDAS
    # =====================================================================
    {
        "id": "SCP-0064-2019-S2",
        "scp_numero": "SCP 0064/2019-S2",
        "sala": "Sala Segunda",
        "materia": "Civil",
        "submateria": "Contrataciones Estatales y Cobro de Deudas",
        "tema": "Retención indebida de pagos en contratos de obras y servicios del Estado (Ley 1178 y DS 0181)",
        "ratio_decidendi": "Las entidades estatales contratantes (Ministerios, Empresas Públicas, EBC, Gobiernos Autónomos) no pueden retener arbitrariamente planillas de avance, certificados de pago o montos aprobados por actas de recepción provisional o definitiva sin resolución administrativa motivada de controversia contractual. El principio de buena fe y la seguridad jurídica obligan al Estado a cumplir los compromisos patrimoniales contraídos válidamente, siendo procedente el cobro por la vía judicial ejecutiva o coactiva fiscal según la naturaleza del título.",
        "normas_clave": ["D.S. 0181 (NB-SABS)", "Ley 1178 (SAFCO)", "Código Civil Art. 519", "Ley 439 (Código Procesal Civil) Art. 378"],
        "descriptores": ["contrato estatal", "ebc", "ecotraffic", "planillas", "deuda", "retencion", "recepcion definitiva", "empresa publica"]
    },
    {
        "id": "SCP-0112-2018-S3",
        "scp_numero": "SCP 0112/2018-S3",
        "sala": "Sala Tercera",
        "materia": "Civil",
        "submateria": "Procesos de Estructura Monitoria y Ejecutivos",
        "tema": "Exigibilidad de sumas líquidas y exigibles nacidas de contratos bilaterales",
        "ratio_decidendi": "Todo contrato bilateral que contenga una obligación patrimonial de dar suma de dinero líquida y de plazo vencido adquiere fuerza ejecutiva cuando se acredita el cumplimiento de la contraprestación mediante actas de entrega, facturas comerciales o requerimientos notariales no enervados. La ausencia de comprobante de pago bancario por parte del deudor genera presunción de mora y legitimidad de la pretensión de cobro.",
        "normas_clave": ["Código Civil Art. 291", "Código Civil Art. 339", "Ley 439 Art. 375", "Ley 439 Art. 379"],
        "descriptores": ["ejecutivo", "titulo ejecutivo", "mora", "pago", "comprobante bancario", "contrato", "obligacion de dar"]
    },
    {
        "id": "SCP-0451-2017-S2",
        "scp_numero": "SCP 0451/2017-S2",
        "sala": "Sala Segunda",
        "materia": "Civil",
        "submateria": "Contratos Comerciales y Adendas",
        "tema": "Fuerza vinculante de las adendas y contratos modificatorios (Pacta Sunt Servanda)",
        "ratio_decidendi": "Los contratos modificatorios y adendas debidamente suscritas por las partes tienen la misma fuerza vinculante que el contrato principal (art. 519 CC). El contratante demandado no puede oponer excepciones de nulidad sobre adendas que fueron ejecutadas y respecto de las cuales no accionó la vía ordinaria dentro del plazo prescriptivo.",
        "normas_clave": ["Código Civil Art. 519", "Código Civil Art. 520", "Ley 439 Art. 381"],
        "descriptores": ["contrato modificatorio", "adenda", "pacta sunt servanda", "excepciones", "modificacion de plazo"]
    },

    # =====================================================================
    # MATERIA: CONSTITUCIONAL Y ACCIONES DE TUTELA (AMPARO)
    # =====================================================================
    {
        "id": "SCP-0270-2018-S2",
        "scp_numero": "SCP 0270/2018-S2",
        "sala": "Sala Segunda",
        "materia": "Constitucional",
        "submateria": "Acción de Amparo Constitucional",
        "tema": "Principio de subsidiariedad en controversias patrimoniales y contratos administrativos",
        "ratio_decidendi": "La acción de amparo constitucional no constituye una vía sustitutiva ni alternativa de los procesos ordinarios, ejecutivos o contencioso-administrativos para el cobro de deudas contractuales, salvo que se demuestre la existencia de vías de hecho (medidas de facto) manifiestamente lesivas a derechos fundamentales o peligro inminente de daño irreparable que no pueda ser tutelado en la jurisdicción ordinaria.",
        "normas_clave": ["CPE Art. 128", "CPE Art. 129", "Ley 254 (CPCo) Art. 53"],
        "descriptores": ["amparo constitucional", "subsidiariedad", "inmediatez", "deuda contractual", "vias ordinarias"]
    },
    {
        "id": "SCP-0998-2012",
        "scp_numero": "SCP 0998/2012",
        "sala": "Sala Plena",
        "materia": "Constitucional",
        "submateria": "Medidas de Hecho y Tutela Directa",
        "tema": "Excepción al principio de subsidiariedad ante medidas o vías de hecho arbitrarias",
        "ratio_decidendi": "La tutela constitucional directa mediante amparo prescinde de la subsidiariedad cuando una autoridad o particular incurre en vías de hecho, entendidas como actos materiales al margen del ordenamiento jurídico (apropiación ilegítima, retención forzosa sin orden judicial, clausura de hecho). Quien alegue vía de hecho debe acreditar titularidad indiscutible del derecho y la concurrencia material del acto arbitrario.",
        "normas_clave": ["CPE Art. 115", "CPE Art. 128", "Ley 254 Art. 54"],
        "descriptores": ["vias de hecho", "medidas de hecho", "arbitrariedad", "tutela directa", "amparo"]
    },
    {
        "id": "SCP-0340-2016-S2",
        "scp_numero": "SCP 0340/2016-S2",
        "sala": "Sala Segunda",
        "materia": "Constitucional",
        "submateria": "Debido Proceso en Contrataciones Públicas",
        "tema": "Debido proceso y derecho a la defensa en resoluciones contractuales de entidades estatales",
        "ratio_decidendi": "Toda entidad del Estado que pretenda resolver unilateralmente un contrato de obra o servicio bajo el DS 0181 debe notificar formalmente con las notas de intención de resolución, permitiendo al contratista presentar descargos y ejercer su derecho a la defensa antes de consolidar la ejecución de boletas de garantía o retenciones.",
        "normas_clave": ["CPE Art. 115.II", "CPE Art. 117.I", "D.S. 0181 Art. 36"],
        "descriptores": ["debido proceso", "resolucion de contrato", "notificacion", "boletas de garantia", "descargos"]
    },

    # =====================================================================
    # MATERIA: LABORAL Y SOCIAL
    # =====================================================================
    {
        "id": "SCP-0084-2017-S3",
        "scp_numero": "SCP 0084/2017-S3",
        "sala": "Sala Tercera",
        "materia": "Laboral",
        "submateria": "Fuero de Maternidad y Conminatoria",
        "tema": "Inamovilidad laboral de mujer embarazada y del progenitor hasta el año de edad del hijo",
        "ratio_decidendi": "El fuero de maternidad y la inamovilidad laboral del progenitor gozan de tutela directa e inmediata vía acción de amparo constitucional, prescindiendo del principio de subsidiariedad ante el incumplimiento de la conminatoria de reincorporación emitida por la Jefatura Departamental de Trabajo.",
        "normas_clave": ["Ley General del Trabajo", "CPE Art. 48.VI", "D.S. 0012", "D.S. 0495"],
        "descriptores": ["embarazo", "maternidad", "progenitor", "reincorporacion", "inamovilidad", "jefatura de trabajo"]
    },
    {
        "id": "SCP-0177-2012",
        "scp_numero": "SCP 0177/2012",
        "sala": "Sala Plena",
        "materia": "Laboral",
        "submateria": "Estabilidad Laboral Reforzada",
        "tema": "Cumplimiento obligatorio e inexcusable de conminatorias de reincorporación laboral",
        "ratio_decidendi": "Las resoluciones y conminatorias emitidas por las Jefaturas Departamentales de Trabajo que ordenan la reincorporación de un trabajador despedido injustificadamente son de cumplimiento obligatorio e inmediato, no pudiendo el empleador suspender su ejecución por la interposición de recursos administrativos o judiciales.",
        "normas_clave": ["D.S. 28699 Art. 10", "D.S. 0495", "CPE Art. 46"],
        "descriptores": ["despido injustificado", "conminatoria", "reincorporacion", "estabilidad laboral", "salarios devengados"]
    },

    # =====================================================================
    # MATERIA: PENAL Y GARANTÍAS PROCESALES
    # =====================================================================
    {
        "id": "SCP-0011-2021-S2",
        "scp_numero": "SCP 0011/2021-S2",
        "sala": "Sala Segunda",
        "materia": "Penal",
        "submateria": "Medidas Cautelares Personales (Ley 1173)",
        "tema": "Fundamentación y motivación estricta para la detención preventiva bajo la Ley 1173",
        "ratio_decidendi": "La detención preventiva es una medida de carácter excepcionalísimo. Los jueces cautelares deben fundamentar de forma analítica e individualizada los riesgos procesales de fuga (art. 234 CPP) y obstaculización (art. 235 CPP), evaluando de manera preferente medidas sustitutivas conforme a las modificaciones de la Ley 1173.",
        "normas_clave": ["Ley 1970 (CPP) Art. 233", "Ley 1173 Art. 1", "CPE Art. 23"],
        "descriptores": ["detencion preventiva", "medidas cautelares", "ley 1173", "riesgo de fuga", "obstaculizacion"]
    },
    {
        "id": "SCP-0010-2018-S2",
        "scp_numero": "SCP 0010/2018-S2",
        "sala": "Sala Segunda",
        "materia": "Penal",
        "submateria": "Tipicidad y Delitos de Contenido Patrimonial",
        "tema": "Prohibición de criminalizar controversias contractuales de naturaleza civil o comercial",
        "ratio_decidendi": "El incumplimiento de obligaciones nacidas de un contrato civil o comercial no constituye por sí mismo delito de estafa o estelionato, salvo que se demuestre dolo antecedente o engaño estructurado al momento de celebrar el negocio. El Ministerio Público y los jueces de garantías deben rechazar la instrumentalización del proceso penal como mecanismo de presión para el cobro de deudas.",
        "normas_clave": ["Código Penal Art. 335 (Estafa)", "CPE Art. 115", "CPE Art. 117"],
        "descriptores": ["estafa", "contrato civil", "cobro de deudas", "instrumentalizacion penal", "principio de tipicidad"]
    }
]
