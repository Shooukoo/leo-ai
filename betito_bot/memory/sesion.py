"""Sesión de conversación en curso.

Cada agente guarda una memoria por sesión. El orquestador fija la sesión al
atender un mensaje; es un ContextVar porque cada ejecución corre en su hilo y
`delegate` llama a otros agentes sin pasarles la sesión.
"""

from contextvars import ContextVar

SESION_POR_DEFECTO = "default"
MAX_SESIONES = 200  # por agente; al pasarse se descarta la que lleva más tiempo sin usarse

SESION: ContextVar[str] = ContextVar("sesion", default=SESION_POR_DEFECTO)
