"""Skills: `betito_bot/skills/<nombre>/SKILL.md` con frontmatter `name` y `description`.

Al arrancar solo se lee el frontmatter; el cuerpo (las instrucciones) se lee del
disco cuando la skill se invoca, ya sea con `/nombre` o con la tool `usar_skill`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from betito_bot.core import frontmatter


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    ruta: Path

    def leer(self) -> str:
        """Cuerpo de la skill, leído bajo demanda."""
        return frontmatter.leer(self.ruta)[1]


def cargar_skills(directorio: Path, avisos: list[str] | None = None) -> dict[str, Skill]:
    """Lee el frontmatter de cada `SKILL.md`. Las inválidas se omiten y se anotan en `avisos`."""
    avisos = [] if avisos is None else avisos
    skills: dict[str, Skill] = {}
    if not directorio.is_dir():
        return skills
    for ruta in sorted(directorio.glob("*/SKILL.md")):
        try:
            meta, _ = frontmatter.leer(ruta)
        except (OSError, frontmatter.FrontmatterInvalido) as e:
            avisos.append(f"Skill ignorada {ruta}: {e}")
            continue
        nombre = str(meta.get("name") or ruta.parent.name)
        descripcion = str(meta.get("description") or "")
        if not descripcion:
            avisos.append(f"Skill ignorada {ruta}: falta 'description'")
            continue
        skills[nombre] = Skill(nombre, descripcion, ruta)
    return skills


def mensaje_para_agente(skill: Skill, argumentos: str) -> str:
    """Texto que recibe el agente al invocar `/skill argumentos`.

    Si los argumentos empiezan con `@agente`, la mención va al principio para que
    el orquestador la respete.
    """
    mencion = ""
    if argumentos.startswith("@"):
        mencion, _, argumentos = argumentos.partition(" ")
        mencion += " "
    peticion = argumentos.strip() or "(sin detalles adicionales)"
    return (
        f"{mencion}Aplica la skill «{skill.name}». Instrucciones:\n\n{skill.leer()}\n\n"
        f"Petición del usuario: {peticion}"
    )
