"""Agentes dedicados definidos en `betito_bot/agents/<nombre>.md`, junto a los de Python.

Frontmatter: `name`, `description`, `tools` (lista de tools permitidas, tomadas
del catálogo de los agentes ya registrados) y `model` opcional. El cuerpo es el
prompt de sistema. Cada uno se construye como un `ToolAgent` normal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from betito_bot.agents.tool_agent import ToolAgent
from betito_bot.core import frontmatter

NOMBRE_VALIDO = re.compile(r"^\w+$")  # debe poder escribirse como @nombre


@dataclass(frozen=True)
class DefinicionAgente:
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    model: str | None = None


class AgenteMarkdown(ToolAgent):
    """`ToolAgent` cuyo prompt y tools vienen de un archivo `.md`."""

    def __init__(self, definicion: DefinicionAgente, client, catalogo: dict[str, tuple[dict, Callable[..., dict]]]):
        faltantes = [t for t in definicion.tools if t not in catalogo]
        if faltantes:
            raise ValueError(f"tools desconocidas en {definicion.name}: {', '.join(faltantes)}")
        self.name = definicion.name
        self.descripcion = definicion.description
        super().__init__(
            client,
            system_prompt=definicion.system_prompt,
            tools_schema=[catalogo[t][0] for t in definicion.tools],
            registry={t: catalogo[t][1] for t in definicion.tools},
            model=definicion.model,
        )


def leer_definicion(ruta: Path) -> DefinicionAgente:
    meta, cuerpo = frontmatter.leer(ruta)
    nombre = str(meta.get("name") or ruta.stem).lower()
    if not NOMBRE_VALIDO.match(nombre):
        raise ValueError(f"nombre de agente no válido: {nombre!r} (solo letras, números y _)")
    if not meta.get("description"):
        raise ValueError("falta 'description'")
    if not cuerpo:
        raise ValueError("falta el prompt de sistema (cuerpo del archivo)")
    tools = meta.get("tools") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    return DefinicionAgente(nombre, str(meta["description"]), cuerpo, list(tools), meta.get("model") or None)


def cargar_definiciones(directorio: Path, avisos: list[str] | None = None) -> list[DefinicionAgente]:
    """Lee cada `*.md` del directorio; los inválidos se omiten y se anotan en `avisos`."""
    avisos = [] if avisos is None else avisos
    definiciones = []
    if not directorio.is_dir():
        return definiciones
    for ruta in sorted(directorio.glob("*.md")):
        if ruta.name.upper() == "README.MD":
            continue
        try:
            definiciones.append(leer_definicion(ruta))
        except (OSError, ValueError) as e:
            avisos.append(f"Agente ignorado {ruta}: {e}")
    return definiciones
