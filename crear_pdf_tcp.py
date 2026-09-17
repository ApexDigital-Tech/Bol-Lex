import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

os.makedirs("sentencias_pdf", exist_ok=True)
pdf_path = os.path.join("sentencias_pdf", "SCP_0084_2017_S3.pdf")

doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()
normal = styles["Normal"]
title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=12, leading=14)

historia = [
    Paragraph("TRIBUNAL CONSTITUCIONAL PLURINACIONAL", title_style),
    Paragraph("SENTENCIA CONSTITUCIONAL PLURINACIONAL 0084/2017-S3", title_style),
    Paragraph("Sucre, 20 de febrero de 2017", normal),
    Paragraph("SALA TERCERA", normal),
    Paragraph("Magistrado Relator: Dr. Ruddy José Flores Monterrey", normal),
    Spacer(1, 15),
    Paragraph("III. FUNDAMENTOS JURÍDICOS DEL FALLO", title_style),
    Paragraph(
        "El fuero de maternidad y la inamovilidad laboral de la mujer embarazada y del progenitor "
        "gozan de tutela directa e inmediata a través de la acción de amparo constitucional. "
        "El empleador que incumpla una conminatoria de reincorporación emitida por la Jefatura "
        "Departamental de Trabajo vulnera derechos fundamentales de orden primario, no siendo "
        "exigible el agotamiento de la vía judicial ordinaria laboral en razón a la protección "
        "prioritaria del interés superior del menor y la subsistencia de la madre trabajadora.",
        normal
    ),
    Spacer(1, 15),
    Paragraph("POR TANTO", title_style),
    Paragraph("El Tribunal Constitucional Plurinacional CONCEDE la tutela solicitada.", normal)
]

doc.build(historia)
print(f"PDF del TCP generado exitosamente en: {pdf_path}")