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

class ExtractorDocumental:
    _motor_ocr = None
    _error_ocr = None

    @classmethod
    def obtener_motor_ocr(cls):
        """Carga perezosa del motor OCR con captura de error descriptivo."""
        if cls._motor_ocr is None and cls._error_ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                cls._motor_ocr = RapidOCR()
            except Exception as e:
                cls._error_ocr = str(e)
        return cls._motor_ocr, cls._error_ocr

    @classmethod
    def extraer_texto(cls, ruta_o_buffer, nombre_archivo: str, carpeta_caso: str = "") -> Tuple[str, Dict[str, Any]]:
        """
        Extrae el contenido textual y retorna (texto, diagnostico_metadatos).
        Busca en caché (.cache.txt / .ocr_cache.txt), intenta digital nativo y luego OCR local.
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

        # -------------------------------------------------------------
        # 0. Verificación previa de Caché en disco
        # -------------------------------------------------------------
        if carpeta_caso:
            posibles_caches = [
                os.path.join(carpeta_caso, f"{nombre_archivo}.cache.txt"),
                os.path.join(carpeta_caso, f"{nombre_archivo}.ocr_cache.txt"),
                os.path.join(carpeta_caso, f"{nombre_archivo}.txt")
            ]
            for r_cache in posibles_caches:
                if os.path.exists(r_cache):
                    try:
                        with open(r_cache, "r", encoding="utf-8", errors="ignore") as fc:
                            texto_c = fc.read().strip()
                            if len(texto_c) > 60:
                                diag.update({
                                    "metodo": "cache_existente",
                                    "caracteres": len(texto_c),
                                    "legible": True
                                })
                                return texto_c, diag
                    except Exception:
                        pass

        try:
            # ---------------------------------------------------------
            # 1. Archivos de texto plano (.txt)
            # ---------------------------------------------------------
            if nl.endswith(".txt"):
                if hasattr(ruta_o_buffer, "read"):
                    texto = ruta_o_buffer.read().decode("utf-8", errors="ignore")
                else:
                    with open(ruta_o_buffer, "r", encoding="utf-8", errors="ignore") as f:
                        texto = f.read()
                diag.update({"metodo": "texto_plano", "caracteres": len(texto), "legible": len(texto.strip()) > 10})
                return texto, diag

            # ---------------------------------------------------------
            # 2. Documentos de Word (.docx)
            # ---------------------------------------------------------
            elif nl.endswith(".docx"):
                doc = Document(ruta_o_buffer)
                parrafos = [p.text for p in doc.paragraphs if p.text.strip()]
                for tabla in doc.tables:
                    for fila in tabla.rows:
                        parrafos.append(" | ".join([celda.text.strip() for celda in fila.cells if celda.text.strip()]))
                texto = "\n".join(parrafos)
                diag.update({"metodo": "docx_nativo", "caracteres": len(texto), "legible": len(texto.strip()) > 20})
                return texto, diag

            # ---------------------------------------------------------
            # 3. Archivos PDF (.pdf)
            # ---------------------------------------------------------
            elif nl.endswith(".pdf"):
                reader = PdfReader(ruta_o_buffer)
                num_pags = len(reader.pages)
                diag["paginas"] = num_pags

                # Intento 1: Extracción digital embebida
                paginas_digitales = []
                for idx, p in enumerate(reader.pages):
                    t = p.extract_text() or ""
                    if len(t.strip()) > 20:
                        paginas_digitales.append(f"[Página {idx+1}]\n{t.strip()}")

                texto_digital = "\n\n".join(paginas_digitales).strip()
                if len(texto_digital) > 100:
                    diag.update({"metodo": "pdf_digital", "caracteres": len(texto_digital), "legible": True})
                    if carpeta_caso:
                        with open(os.path.join(carpeta_caso, f"{nombre_archivo}.cache.txt"), "w", encoding="utf-8") as fc:
                            fc.write(texto_digital)
                    return texto_digital, diag

                # Intento 2: OCR Local de alta precisión (para documentos escaneados)
                motor_ocr, err_ocr = cls.obtener_motor_ocr()
                if motor_ocr is not None:
                    try:
                        import pypdfium2 as pdfium
                        if isinstance(ruta_o_buffer, str):
                            doc_pdf = pdfium.PdfDocument(ruta_o_buffer)
                        else:
                            if hasattr(ruta_o_buffer, "seek"):
                                ruta_o_buffer.seek(0)
                            doc_pdf = pdfium.PdfDocument(ruta_o_buffer.read())

                        paginas_ocr = []
                        max_pags = min(len(doc_pdf), 15)  # Procesar hasta 15 páginas por contrato/acta
                        for idx in range(max_pags):
                            pagina = doc_pdf[idx]
                            bitmap = pagina.render(scale=1.5)
                            pil_img = bitmap.to_pil().convert("RGB")
                            img_arr = np.array(pil_img)
                            res, _ = motor_ocr(img_arr)
                            if res:
                                lineas = [l[1] for l in res if l and len(l) > 1]
                                paginas_ocr.append(f"[Página {idx+1} (OCR)]\n" + "\n".join(lineas))

                        texto_ocr = "\n\n".join(paginas_ocr).strip()
                        if len(texto_ocr) > 50:
                            diag.update({
                                "metodo": "rapidocr_local",
                                "caracteres": len(texto_ocr),
                                "legible": True
                            })
                            if carpeta_caso:
                                with open(os.path.join(carpeta_caso, f"{nombre_archivo}.cache.txt"), "w", encoding="utf-8") as fc:
                                    fc.write(texto_ocr)
                                with open(os.path.join(carpeta_caso, f"{nombre_archivo}.ocr_cache.txt"), "w", encoding="utf-8") as fc:
                                    fc.write(texto_ocr)
                            return texto_ocr, diag
                    except Exception as e:
                        diag["advertencia"] = f"Error ejecutando OCR local: {e}"
                else:
                    diag["advertencia"] = f"Motor OCR no disponible en este entorno: {err_ocr}"

                # Si todo falla
                diag["legible"] = False
                msg_fallo = f"[Documento {nombre_archivo}: Escaneo sin capa de texto digital ni OCR disponible en el host]"
                return msg_fallo, diag

            return f"[Formato no soportado: {nombre_archivo}]", diag

        except Exception as e:
            diag["advertencia"] = f"Error procesando archivo: {e}"
            diag["legible"] = False
            return f"[Error en {nombre_archivo}: {e}]", diag

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
