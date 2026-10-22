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
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
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
        self.modelo_activo: str = "llama-3.1-8b-instant"

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
        Ejecuta la inferencia con fallback dinámico y bucle agéntico de auto-continuación si finish_reason == 'length'.
        """
        if not self.cliente:
            # Reintento tardío de resolución de credenciales
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

        tokens_salida = max_tokens if max_tokens else (2048 if json_mode else 3500)
        intentos = [self.modelo_activo] + [m for m in self.modelos_disponibles if m != self.modelo_activo]
        ultimo_error = None

        # Estimación conservadora de tokens del prompt (español ~3.2 caracteres por token)
        caracteres_totales = sum(len(m.get("content", "")) for m in mensajes)
        tokens_estimados = int(caracteres_totales / 3.2)

        for mod in intentos:
            es_modelo_8k = any(k in mod.lower() for k in ["8192", "gemma", "qwen"])
            
            # Ajuste preventivo para modelos de contexto estrecho (8k)
            tokens_efectivos = tokens_salida
            if es_modelo_8k:
                # Si el prompt ya consume la mayor parte de la ventana de 8k, saltar a modelo 128k
                if tokens_estimados > 5500:
                    continue
                tokens_efectivos = max(1000, min(tokens_salida, 7800 - tokens_estimados))

            try:
                params: Dict[str, Any] = {
                    "model": mod,
                    "messages": mensajes,
                    "temperature": temperatura,
                    "max_tokens": tokens_efectivos
                }
                if json_mode:
                    params["response_format"] = {"type": "json_object"}

                res = self.cliente.chat.completions.create(**params)
                contenido_inicial = res.choices[0].message.content or ""
                finish_reason = getattr(res.choices[0], "finish_reason", "stop")

                # Bucle Agéntico de Continuación si fue truncado por longitud
                if auto_continuar and not json_mode and finish_reason == "length":
                    contenido_acumulado = contenido_inicial
                    mensajes_loop = list(mensajes)
                    ciclos_cont = 0
                    max_ciclos = 3

                    while finish_reason == "length" and ciclos_cont < max_ciclos:
                        ciclos_cont += 1
                        mensajes_loop.append({"role": "assistant", "content": contenido_acumulado})
                        mensajes_loop.append({
                            "role": "user",
                            "content": (
                                "Continúa redactando exactamente desde donde se interrumpió la última palabra del texto anterior. "
                                "Prohibido repetir lo ya redactado. Mantén la estructura formal, coherencia técnica y completa todas las secciones faltantes hasta concluir."
                            )
                        })
                        p_cont = dict(params)
                        p_cont["messages"] = mensajes_loop
                        p_cont["max_tokens"] = tokens_efectivos
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

                # 1. Recuperación automática ante Error 400 por límite de longitud de contexto
                if any(k in err_msg for k in ["reduce the length of the messages", "context_length_exceeded", "maximum context length", "too large"]):
                    # Conmutar de inmediato a modelos con ventana masiva de 128k (Llama 3.3 / Llama 3.1)
                    modelos_128k = [m for m in self.modelos_disponibles if any(k in m for k in ["3.3", "3.1", "mixtral"])]
                    recuperado = False
                    for m128 in modelos_128k:
                        if m128 != mod:
                            try:
                                p128 = dict(params)
                                p128["model"] = m128
                                p128["max_tokens"] = 3000
                                res128 = self.cliente.chat.completions.create(**p128)
                                self.modelo_activo = m128
                                return res128.choices[0].message.content or ""
                            except Exception:
                                continue

                    # Si aún excede, recortar preventivamente los mensajes de entrada y reintentar
                    try:
                        mensajes_recortados = []
                        for m in mensajes:
                            c = m.get("content", "")
                            if len(c) > 4000:
                                c = c[:3500] + "\n[...Texto sintetizado para preservar ventana de contexto...]"
                            mensajes_recortados.append({"role": m["role"], "content": c})
                        p_rec = dict(params)
                        p_rec["messages"] = mensajes_recortados
                        p_rec["max_tokens"] = 1500
                        res_rec = self.cliente.chat.completions.create(**p_rec)
                        self.modelo_activo = mod
                        return res_rec.choices[0].message.content or ""
                    except Exception:
                        pass
                    continue

                # 2. Backoff defensivo ante saturación de cuota TPM/RPM (429)
                if "rate_limit" in err_msg or "429" in err_msg:
                    time.sleep(2.0)
                    continue

                # 3. Conmutar si el modelo fue deprecado o no está habilitado (404)
                if any(k in err_msg for k in ["model_not_found", "does not exist", "404", "decommissioned"]):
                    continue

                raise e

        if ultimo_error:
            raise ultimo_error
        return ""
