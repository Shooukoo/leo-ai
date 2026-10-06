"""Arma el orquestador real con skills y agentes `.md` según la configuración."""

from __future__ import annotations

import os

from betito_bot.agents.tool_agent import DEFAULT_MODEL
from betito_bot.core.agentes import AgenteMarkdown, cargar_definiciones
from betito_bot.core.config import Config
from betito_bot.core.skills import cargar_skills
from betito_bot.orchestrator.router import Orchestrator
from betito_bot.seguridad.guardian import Guardian


def construir_orquestador(config: Config, client) -> tuple[Orchestrator, list[str]]:
    """Devuelve el orquestador y la lista de avisos de carga (skills o agentes inválidos)."""
    avisos: list[str] = []
    guardian = Guardian(
        client,
        model=os.getenv("GUARDIAN_MODEL") or os.getenv("LLM_MODEL", DEFAULT_MODEL),
        usar_llm=os.getenv("BETITO_GUARDIAN", "1") != "0",
    )
    orchestrator = Orchestrator(client, skills=cargar_skills(config.skills_dir, avisos), guardian=guardian)
    catalogo = orchestrator.catalogo_tools()
    for definicion in cargar_definiciones(config.agentes_dir, avisos):
        if definicion.name in orchestrator.agents:
            avisos.append(f"Agente {definicion.name} ignorado: ya existe uno con ese nombre.")
            continue
        try:
            orchestrator.registrar(AgenteMarkdown(definicion, client, catalogo))
        except ValueError as e:
            avisos.append(f"Agente {definicion.name} ignorado: {e}")
    return orchestrator, avisos
