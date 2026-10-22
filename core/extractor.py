"""
Módulo de Procesamiento y Extracción Documental Certificada.
Garantiza lectura digital nativa, OCR local para escaneos y diagnóstico de legibilidad.
"""
import io
import os
import zipfile
import shutil
from typing import Tuple, Dict, Any, List
import numpy as np
from pypdf import PdfReader
from docx import Document

# Carga segura y defensiva del motor OCR local
OCR_DISPONIBLE = False
motor_ocr_local = None

try:
    from rapidocr_onnxruntime import RapidOCR
    import pypdfium2 as pdfium
    motor_ocr_local = RapidOCR()
    OCR_DISPONIBLE = True
except Exception:
    OCR_DISPONIBLE = False

class ExtractorDocumental:
    @staticmethod
    def extraer_texto(ruta_o_buffer, nombre_archivo: str, carpeta_caso: str = "") -> Tuple[str, Dict[str, Any]]:
        """
        Extrae el contenido textual y retorna (texto, diagnostico_metadatos).
        Diagnóstico incluye: legible (bool), método (digital/ocr), páginas, caracteres.
        """
        nl = nombre_archivo.lower()
        diag = {
            "archivo": nombre_archivo,
            "metodo": "desconocido",
            "caracteres": 0,
            "paginas": 1,
            "legible": False,
            "advertencia": ""
        }

        try:
            # Archivo de texto plano
            if nl.endswith(".txt"):
                if hasattr(ruta_o_buffer, "read"):
                    texto = ruta_o_buffer.read().decode("utf-8", errors="ignore")
                else:
                    with open(ruta_o_buffer, "r", encoding="utf-8", errors="ignore") as f:
                        texto = f.read()
                diag.update({"metodo": "texto_plano", "caracteres": len(texto), "legible": len(texto.strip()) > 10})
                return texto, diag

            # Documento de Word (.docx)
            elif nl.endswith(".docx"):
                doc = Document(ruta_o_buffer)
                parrafos = [p.text for p in doc.paragraphs if p.text.strip()]
                # También tablas
                for tabla in doc.tables:
                    for fila in tabla.rows:
                        parrafos.append(" | ".join([celda.text.strip() for celda in fila.cells if celda.text.strip()]))
                texto = "\n".join(parrafos)
                diag.update({"metodo": "docx_nativo", "caracteres": len(texto), "legible": len(texto.strip()) > 20})
                return texto, diag

            # Archivo PDF
            elif nl.endswith(".pdf"):
                # Verificar caché si existe carpeta de caso
                if carpeta_caso:
                    ruta_cache = os.path.join(carpeta_caso, f"{nombre_archivo}.cache.txt")
                    if os.path.exists(ruta_cache):
                        with open(ruta_cache, "r", encoding="utf-8") as fc:
                            texto_cache = fc.read()
                            if len(texto_cache.strip()) > 50:
                                diag.update({"metodo": "cache_local", "caracteres": len(texto_cache), "legible": True})
                                return texto_cache, diag

                reader = PdfReader(ruta_o_buffer)
                num_pags = len(reader.pages)
                diag["paginas"] = num_pags
                
                # 1. Intento de extracción digital
                paginas_texto = []
                for idx, p in enumerate(reader.pages):
                    t = p.extract_text() or ""
                    if t.strip():
                        paginas_texto.append(f"[Página {idx+1}]\n{t.strip()}")
                
                texto_digital = "\n\n".join(paginas_texto).strip()
                
                # Si el PDF contiene más de 120 caracteres de texto digital, es legible directamente
                if len(texto_digital) > 120:
                    diag.update({"metodo": "pdf_digital", "caracteres": len(texto_digital), "legible": True})
                    if carpeta_caso:
                        with open(os.path.join(carpeta_caso, f"{nombre_archivo}.cache.txt"), "w", encoding="utf-8") as fc:
                            fc.write(texto_digital)
                    return texto_digital, diag

                # 2. Si no tiene texto embebido, intentar OCR local si está disponible
                if OCR_DISPONIBLE:
                    try:
                        import pypdfium2 as pdfium
                        if isinstance(ruta_o_buffer, str):
                            doc_pdf = pdfium.PdfDocument(ruta_o_buffer)
                        else:
                            if hasattr(ruta_o_buffer, "seek"):
                                ruta_o_buffer.seek(0)
                            doc_pdf = pdfium.PdfDocument(ruta_o_buffer.read())
                        
                        paginas_ocr = []
                        max_pags = min(len(doc_pdf), 10)  # Procesar hasta 10 páginas para expedientes
                        for idx in range(max_pags):
                            pagina = doc_pdf[idx]
                            bitmap = pagina.render(scale=1.5)
                            pil_img = bitmap.to_pil().convert("RGB")
                            img_arr = np.array(pil_img)
                            res, _ = motor_ocr_local(img_arr)
                            if res:
                                lineas = [l[1] for l in res if l and len(l) > 1]
                                paginas_ocr.append(f"[Página {idx+1} (OCR)]\n" + "\n".join(lineas))

                        texto_ocr = "\n\n".join(paginas_ocr).strip()
                        if len(texto_ocr) > 80:
                            diag.update({"metodo": "rapidocr_local", "caracteres": len(texto_ocr), "legible": True})
                            if carpeta_caso:
                                with open(os.path.join(carpeta_caso, f"{nombre_archivo}.cache.txt"), "w", encoding="utf-8") as fc:
                                    fc.write(texto_ocr)
                            return texto_ocr, diag
                    except Exception as e:
                        diag["advertencia"] = f"Fallo motor OCR: {e}"

                # Si no se pudo extraer texto
                diag["legible"] = False
                diag["advertencia"] = "Documento escaneado o imagen de baja resolución sin capa de texto."
                mensaje_vacio = f"[ADVERTENCIA: El archivo '{nombre_archivo}' es un escaneo sin capa de texto digital legible. Se requiere versión en alta resolución o digitalizada para cotejo probatorio]."
                return mensaje_vacio, diag

            return f"[Formato no soportado: {nombre_archivo}]", diag

        except Exception as e:
            diag["advertencia"] = f"Error crítico de lectura: {e}"
            diag["legible"] = False
            return f"[Error al leer {nombre_archivo}: {e}]", diag

    @staticmethod
    def descomprimir_zip(buffer_o_ruta, carpeta_destino: str) -> List[str]:
        archivos_extraidos = []
        with zipfile.ZipFile(buffer_o_ruta, 'r') as zip_ref:
            for info in zip_ref.infolist():
                nombre = os.path.basename(info.filename)
                if not nombre:
                    continue
                if nombre.lower().endswith((".pdf", ".docx", ".txt")):
                    destino = os.path.join(carpeta_destino, nombre)
                    with zip_ref.open(info) as fuente, open(destino, "wb") as f_dest:
                        shutil.copyfileobj(fuente, f_dest)
                    archivos_extraidos.append(nombre)
        return archivos_extraidos
