"""Parseo de archivos Markdown con frontmatter YAML (`---` ... `---`).

Soporta el subconjunto de YAML que usan skills y agentes, sin depender de PyYAML:
`clave: valor`, cadenas con o sin comillas, listas en línea `[a, b]` y listas
en bloque (`- a`). Los comentarios `#` al inicio de línea se ignoran.
"""

from __future__ import annotations

import re
from pathlib import Path

_DELIMITADOR = re.compile(r"^---\s*$")


class FrontmatterInvalido(ValueError):
    pass


def _escalar(valor: str) -> str:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor


def _valor(valor: str) -> str | list[str]:
    valor = valor.strip()
    if valor.startswith("[") and valor.endswith("]"):
        interior = valor[1:-1].strip()
        return [_escalar(v) for v in interior.split(",")] if interior else []
    return _escalar(valor)


def parsear(texto: str) -> tuple[dict, str]:
    """Devuelve `(metadatos, cuerpo)`. Sin frontmatter, los metadatos quedan vacíos."""
    lineas = texto.splitlines()
    if not lineas or not _DELIMITADOR.match(lineas[0]):
        return {}, texto.strip()
    try:
        fin = next(i for i in range(1, len(lineas)) if _DELIMITADOR.match(lineas[i]))
    except StopIteration:
        raise FrontmatterInvalido("frontmatter sin cierre '---'") from None

    datos: dict = {}
    clave_lista: str | None = None
    for n, linea in enumerate(lineas[1:fin], start=2):
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s*(.*)$", linea) or re.match(r"^-\s+(.*)$", linea)
        if item and clave_lista is not None:
            datos[clave_lista].append(_escalar(item.group(1)))
            continue
        par = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", linea)
        if not par:
            raise FrontmatterInvalido(f"línea {n} no válida: {linea!r}")
        clave, valor = par.groups()
        if valor.strip():
            datos[clave] = _valor(valor)
            clave_lista = None
        else:
            datos[clave] = []
            clave_lista = clave
    return datos, "\n".join(lineas[fin + 1:]).strip()


def leer(ruta: Path) -> tuple[dict, str]:
    return parsear(ruta.read_text(encoding="utf-8"))
