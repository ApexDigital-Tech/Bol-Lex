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

        tokens_salida = max_tokens if max_tokens else (2048 if json_mode else 4096)
        intentos = [self.modelo_activo] + [m for m in self.modelos_disponibles if m != self.modelo_activo]
        ultimo_error = None

        for mod in intentos:
            try:
                params: Dict[str, Any] = {
                    "model": mod,
                    "messages": mensajes,
                    "temperature": temperatura,
                    "max_tokens": tokens_salida
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
                        p_cont["max_tokens"] = tokens_salida
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

                # Backoff defensivo ante saturación de cuota TPM/RPM
                if "rate_limit" in err_msg or "429" in err_msg:
                    time.sleep(2.0)
                    continue

                # Conmutar si el modelo fue deprecado o no está habilitado
                if any(k in err_msg for k in ["model_not_found", "does not exist", "404", "decommissioned"]):
                    continue

                raise e

        if ultimo_error:
            raise ultimo_error
        return ""
