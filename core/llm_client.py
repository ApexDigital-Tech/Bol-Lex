"""
Módulo de Conectividad y Resiliencia con el Motor de Inferencia LLM (Groq).
Implementa auto-detección dinámica de modelos, dry-run con ping y fallback en cascada.
"""
import os
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
        self.cliente = Groq(api_key=self.api_key)
        self.modelos_disponibles: List[str] = []
        self.modelo_activo: str = "llama-3.1-8b-instant"
        self._inicializar_modelos()

    def _inicializar_modelos(self):
        """Descubre los modelos activos de la cuenta y realiza una prueba en caliente."""
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
        json_mode: bool = False
    ) -> str:
        """
        Ejecuta la inferencia con fallback dinámico ante errores 404, rate_limit o model_not_found.
        """
        intentos = [self.modelo_activo] + [m for m in self.modelos_disponibles if m != self.modelo_activo]
        ultimo_error = None

        for mod in intentos:
            try:
                params: Dict[str, Any] = {
                    "model": mod,
                    "messages": mensajes,
                    "temperature": temperatura
                }
                if max_tokens:
                    params["max_tokens"] = max_tokens
                if json_mode:
                    params["response_format"] = {"type": "json_object"}

                res = self.cliente.chat.completions.create(**params)
                self.modelo_activo = mod
                return res.choices[0].message.content or ""
            except Exception as e:
                err_msg = str(e).lower()
                ultimo_error = e
                # Conmutar si el modelo no existe o la cuenta no tiene acceso
                if any(k in err_msg for k in ["model_not_found", "does not exist", "404", "rate_limit"]):
                    continue
                raise e

        if ultimo_error:
            raise ultimo_error
        return ""
