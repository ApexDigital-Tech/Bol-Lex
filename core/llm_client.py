"""
Módulo de Conectividad y Resiliencia con el Motor de Inferencia LLM (Groq).
Implementa auto-detección dinámica de modelos, dry-run con ping y fallback en cascada.
"""
import os
import time
from typing import List, Dict, Any, Optional
from groq import Groq

# Modelos candidatos ordenados por capacidad de razonamiento jurídico y velocidad
CANDIDATOS_PRIORITARIOS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "qwen/qwen3.8-27b",
]

class MotorLLM:
    def __init__(self, api_key: Optional[str] = None):
        if not api_key:
            api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GROQ_API_KEY", "")
            except Exception:
                api_key = ""
                
        self.api_key = api_key
        self.cliente = None
        self.modelos_disponibles: List[str] = list(CANDIDATOS_PRIORITARIOS)
        self.modelo_activo: str = "llama-3.3-70b-versatile"

        if self.api_key:
            try:
                self.cliente = Groq(api_key=self.api_key)
                self._inicializar_modelos()
            except Exception:
                self.cliente = None

    def actualizar_api_key(self, nueva_key: str):
        """Permite inyectar o actualizar la API key en caliente."""
        if nueva_key and nueva_key != self.api_key:
            self.api_key = nueva_key
            try:
                self.cliente = Groq(api_key=self.api_key)
                self._inicializar_modelos()
            except Exception:
                pass

    def _inicializar_modelos(self):
        """Descubre los modelos activos de la cuenta y realiza una prueba en caliente."""
        if not self.cliente:
            return

        ids_cuenta = []
        try:
            modelos = self.cliente.models.list()
            ids_cuenta = [
                m.id for m in modelos.data 
                if not any(k in m.id.lower() for k in ["guard", "whisper", "orpheus", "vision"])
            ]
        except Exception:
            pass

        # Priorizar candidatos reconocidos que figuren en la cuenta
        lista_ordenada = [c for c in CANDIDATOS_PRIORITARIOS if c in ids_cuenta]
        for m in ids_cuenta:
            if m not in lista_ordenada:
                lista_ordenada.append(m)
        for c in CANDIDATOS_PRIORITARIOS:
            if c not in lista_ordenada:
                lista_ordenada.append(c)

        self.modelos_disponibles = lista_ordenada

        # Dry-run test en caliente
        for cand in self.modelos_disponibles:
            try:
                self.cliente.chat.completions.create(
                    model=cand,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=2
                )
                self.modelo_activo = cand
                break
            except Exception:
                continue

    def cambiar_modelo(self, nuevo_modelo: str) -> bool:
        if nuevo_modelo in self.modelos_disponibles:
            self.modelo_activo = nuevo_modelo
            return True
        return False

    def invocar(
        self, 
        mensajes: List[Dict[str, str]], 
        temperatura: float = 0.05, 
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        auto_continuar: bool = True
    ) -> str:
        """
        Ejecuta la inferencia con blindaje proactivo contra error 400 (TPM/Context Limit) y bucle de continuación ligero.
        """
        if not self.cliente:
            if not self.api_key:
                self.api_key = os.environ.get("GROQ_API_KEY", "")
            if not self.api_key:
                try:
                    import streamlit as st
                    self.api_key = st.secrets.get("GROQ_API_KEY", "")
                except Exception:
                    pass
            if self.api_key:
                try:
                    self.cliente = Groq(api_key=self.api_key)
                    self._inicializar_modelos()
                except Exception:
                    pass

        if not self.cliente:
            raise RuntimeError("API Key de Groq no configurada. Configure GROQ_API_KEY en el entorno o en la barra lateral.")

        # =====================================================================
        # BLINDAJE PROACTIVO CONTRA ERROR 400 (Groq TPM / Request Budget Ceiling)
        # Techo máximo total de tokens por petición = 4,200 (margen seguro sobre 6,000 TPM)
        # =====================================================================
        MAX_REQUEST_TOTAL_TOKENS = 4200
        
        # 1. Determinar presupuesto de salida base
        if json_mode:
            target_tokens_salida = min(max_tokens or 1000, 1200)
        else:
            target_tokens_salida = min(max_tokens or 1800, 1800)

        # 2. Presupuesto disponible para el prompt (en español ~3.0 caracteres/token)
        presupuesto_prompt_tokens = MAX_REQUEST_TOTAL_TOKENS - target_tokens_salida
        max_chars_prompt = int(presupuesto_prompt_tokens * 3.0)

        # 3. Normalizar y recortar defensivamente los mensajes si superan el presupuesto
        mensajes_procesados = []
        chars_actuales = sum(len(m.get("content", "")) for m in mensajes)
        
        if chars_actuales > max_chars_prompt:
            factor = (max_chars_prompt * 0.95) / chars_actuales
            for m in mensajes:
                c = m.get("content", "")
                if len(c) > 1000:
                    nuevo_tam = int(len(c) * factor)
                    c_rec = c[:nuevo_tam] + "\n[...Texto documental resumido para preservar ventana de procesamiento agéntico...]"
                    mensajes_procesados.append({"role": m["role"], "content": c_rec})
                else:
                    mensajes_procesados.append(dict(m))
        else:
            mensajes_procesados = [dict(m) for m in mensajes]

        # Recalcular tokens reales estimados
        chars_finales = sum(len(m.get("content", "")) for m in mensajes_procesados)
        tokens_prompt_est = int(chars_finales / 3.0)
        tokens_efectivos = max(800, min(target_tokens_salida, MAX_REQUEST_TOTAL_TOKENS - tokens_prompt_est))

        # Lista de modelos a intentar: modelo activo primero, luego los 128k más potentes
        modelos_prioridad = [
            self.modelo_activo,
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama-3.1-70b-versatile",
            "mixtral-8x7b-32768",
        ]
        intentos = []
        for m in modelos_prioridad:
            if m in self.modelos_disponibles and m not in intentos:
                intentos.append(m)
        for m in self.modelos_disponibles:
            if m not in intentos:
                intentos.append(m)

        ultimo_error = None

        for mod in intentos:
            es_8k = any(k in mod.lower() for k in ["8192", "gemma", "qwen"])
            tokens_mod = tokens_efectivos
            mensajes_mod = list(mensajes_procesados)

            # Si es un modelo 8k, ajustar aún más conservador
            if es_8k:
                tokens_mod = min(tokens_efectivos, 1200)

            try:
                params: Dict[str, Any] = {
                    "model": mod,
                    "messages": mensajes_mod,
                    "temperature": temperatura,
                    "max_tokens": tokens_mod
                }
                if json_mode:
                    params["response_format"] = {"type": "json_object"}

                res = self.cliente.chat.completions.create(**params)
                contenido_inicial = res.choices[0].message.content or ""
                finish_reason = getattr(res.choices[0], "finish_reason", "stop")

                # Bucle de Continuación Ligero (no re-envía todo el historial para no saturar tokens)
                if auto_continuar and not json_mode and finish_reason == "length":
                    contenido_acumulado = contenido_inicial
                    ciclos_cont = 0
                    max_ciclos = 2

                    while finish_reason == "length" and ciclos_cont < max_ciclos:
                        ciclos_cont += 1
                        corte_contexto = contenido_acumulado[-600:].strip()
                        mensajes_cont = [
                            {
                                "role": "system", 
                                "content": "Eres un asistente jurídico boliviano de alta precisión técnica. Continúa exactamente donde quedó el texto anterior sin repetir nada."
                            },
                            {
                                "role": "user", 
                                "content": (
                                    f"El texto anterior se interrumpió exactamente en este punto:\n\"\"\"...{corte_contexto}\"\"\"\n\n"
                                    "Continúa redactando a partir de la siguiente palabra. "
                                    "No repitas nada de lo ya escrito. Concluye de forma exhaustiva todas las secciones y fundamentaciones restantes."
                                )
                            }
                        ]
                        p_cont = {
                            "model": mod,
                            "messages": mensajes_cont,
                            "temperature": temperatura,
                            "max_tokens": 1200
                        }
                        res_cont = self.cliente.chat.completions.create(**p_cont)
                        siguiente_tramo = res_cont.choices[0].message.content or ""
                        contenido_acumulado = f"{contenido_acumulado}\n{siguiente_tramo}".strip()
                        finish_reason = getattr(res_cont.choices[0], "finish_reason", "stop")

                    self.modelo_activo = mod
                    return contenido_acumulado

                self.modelo_activo = mod
                return contenido_inicial

            except Exception as e:
                err_msg = str(e).lower()
                ultimo_error = e

                # 1. Recuperación ante 400: reducción drástica de presupuesto y reintento con Llama 3.1 8b o 3.3 70b
                if any(k in err_msg for k in ["reduce the length", "context_length_exceeded", "too large", "400"]):
                    try:
                        m_rescate = "llama-3.1-8b-instant" if "llama-3.1-8b-instant" in self.modelos_disponibles else mod
                        mensajes_mini = []
                        for m in mensajes_mod:
                            c_mini = m.get("content", "")
                            if len(c_mini) > 2000:
                                c_mini = c_mini[:2000] + "\n[...Síntesis ejecutiva...]"
                            mensajes_mini.append({"role": m["role"], "content": c_mini})
                        
                        p_rescate = {
                            "model": m_rescate,
                            "messages": mensajes_mini,
                            "temperature": temperatura,
                            "max_tokens": 1000
                        }
                        if json_mode:
                            p_rescate["response_format"] = {"type": "json_object"}
                        res_resc = self.cliente.chat.completions.create(**p_rescate)
                        self.modelo_activo = m_rescate
                        return res_resc.choices[0].message.content or ""
                    except Exception:
                        pass
                    continue

                # 2. Backoff ante Rate Limit 429
                if "rate_limit" in err_msg or "429" in err_msg:
                    time.sleep(2.0)
                    continue

                # 3. Modelo inexistente o deprecado (404)
                if any(k in err_msg for k in ["model_not_found", "does not exist", "404", "decommissioned"]):
                    continue

                continue

        if ultimo_error:
            raise ultimo_error
        return ""
