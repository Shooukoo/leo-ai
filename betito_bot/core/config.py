"""Configuración desde `config.toml` (raíz del repo o `BETITO_CONFIG`).

Las rutas relativas se resuelven respecto al directorio del archivo de config.
Si el archivo no existe se usan los valores por defecto.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    skills_dir: Path = RAIZ / "betito_bot" / "skills"
    agentes_dir: Path = RAIZ / "betito_bot" / "agents"


def cargar_config(ruta: Path | None = None) -> Config:
    ruta = ruta or Path(os.getenv("BETITO_CONFIG", RAIZ / "config.toml"))
    if not ruta.is_file():
        return Config()
    with ruta.open("rb") as f:
        rutas = tomllib.load(f).get("rutas", {})
    base = ruta.resolve().parent
    defecto = Config()

    def _ruta(clave: str, valor_defecto: Path) -> Path:
        if clave not in rutas:
            return valor_defecto
        p = Path(rutas[clave]).expanduser()
        return p if p.is_absolute() else base / p

    return Config(
        skills_dir=_ruta("skills", defecto.skills_dir),
        agentes_dir=_ruta("agentes", defecto.agentes_dir),
    )
