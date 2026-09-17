import os
import re
import numpy as np
from pypdf import PdfReader
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# =====================================================================
# 1. PARSER AUTOMÁTICO DE PDFs DEL TCP
# =====================================================================
def extraer_datos_pdf(ruta_pdf: str) -> dict:
    """Lee un PDF del TCP y extrae su número, sala y la Ratio Decidendi."""
    reader = PdfReader(ruta_pdf)
    texto_completo = "\n".join([page.extract_text() or "" for page in reader.pages])
    
    # 1. Extraer número de SCP
    match_scp = re.search(r"SENTENCIA CONSTITUCIONAL PLURINACIONAL\s+([0-9]{3,4}/[0-9]{4}-[A-Z0-9]+)", texto_completo, re.IGNORECASE)
    scp_numero = f"SCP {match_scp.group(1).strip()}" if match_scp else os.path.basename(ruta_pdf)
    
    # 2. Extraer Sala
    match_sala = re.search(r"(SALA\s+[A-ZÁÉÍÓÚ\s]+)", texto_completo[:2000], re.IGNORECASE)
    sala = match_sala.group(1).strip() if match_sala else "Sala Constitucional"

    # 3. Extraer Ratio Decidendi (Corte entre Sección III y POR TANTO)
    patron_fundamentos = re.search(
        r"(III\.\s*FUNDAMENTOS\s+JUR[IÍ]DICOS\s+DEL\s+FALLO.*?)(POR\s+TANTO)",
        texto_completo,
        re.DOTALL | re.IGNORECASE
    )
    
    if patron_fundamentos:
        ratio_limpia = patron_fundamentos.group(1).replace("III. FUNDAMENTOS JURÍDICOS DEL FALLO", "").strip()
    else:
        # Fallback si no encuentra el rótulo exacto
        ratio_limpia = texto_completo[:1500]

    return {
        "archivo": os.path.basename(ruta_pdf),
        "scp_numero": scp_numero,
        "sala": sala,
        "ratio_decidendi": ratio_limpia
    }

# =====================================================================
# 2. MOTOR RAG CON ALIMENTACIÓN DESDE CARPETA DE PDFs
# =====================================================================
class MotorRAGDesdeCarpetas:
    def __init__(self, carpeta_pdfs: str = "sentencias_pdf"):
        print(f"Cargando modelo neuronal y analizando PDFs en '{carpeta_pdfs}'...")
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.biblioteca = []
        
        # Leer todos los archivos PDF presentes en la carpeta
        for archivo in os.listdir(carpeta_pdfs):
            if archivo.endswith(".pdf"):
                ruta_completa = os.path.join(carpeta_pdfs, archivo)
                datos_scp = extraer_datos_pdf(ruta_completa)
                self.biblioteca.append(datos_scp)
                print(f" -> [INDEXADO] {datos_scp['scp_numero']} | Archivo: {archivo}")

        if not self.biblioteca:
            raise ValueError(f"No se encontraron PDFs en {carpeta_pdfs}")

        # Vectorizar el contenido extraído de los documentos
        textos = [doc["ratio_decidendi"] for doc in self.biblioteca]
        self.vectores_corpus = self.encoder.encode(textos)
        print("Indexación vectorial completada exitosamente.\n")

    def buscar_precedente(self, hechos_caso: str) -> dict:
        vec_query = self.encoder.encode([hechos_caso])
        similitudes = cosine_similarity(vec_query, self.vectores_corpus)[0]
        mejor_idx = int(np.argmax(similitudes))
        
        resultado = self.biblioteca[mejor_idx].copy()
        resultado["score_similitud"] = float(similitudes[mejor_idx])
        return resultado

# =====================================================================
# 3. EJECUCIÓN DEL CASO CON JURISPRUDENCIA EXTRAÍDA
# =====================================================================
def ejecutar_caso():
    motor = MotorRAGDesdeCarpetas("sentencias_pdf")
    
    # Caso del cliente real que llega al bufete
    caso_cliente = (
        "La empresa Constructora del Sur despidió arbitrariamente a una trabajadora con 6 meses de embarazo. "
        "La Jefatura de Trabajo emitió la conminatoria de reincorporación inmediata pero la gerencia se rehúsa a recibirla."
    )

    print("="*75)
    print("CONSULTA ENTRANTE AL BUFETE:")
    print(f"\"{caso_cliente}\"")
    print("="*75)

    # El sistema busca en el corpus extraído del PDF
    precedente = motor.buscar_precedente(caso_cliente)

    print("\nRESULTADO DEL ANÁLISIS JURÍDICO:")
    print(f"• Precedente Identificado: {precedente['scp_numero']} ({precedente['sala']})")
    print(f"• Grado de Similitud:      {precedente['score_similitud']:.4f}")
    print(f"• Ratio Decidendi Extraída del PDF:\n  \"{precedente['ratio_decidendi']}\"")
    print("-" * 75)
    print("HOJA DE RUTA RECOMENDADA:")
    print("1. Interponer de forma inmediata Acción de Amparo Constitucional.")
    print("2. Invocar la excepción al principio de subsidiariedad establecida en la conminatoria laboral y la SCP citada.")
    print("="*75)

if __name__ == "__main__":
    ejecutar_caso()