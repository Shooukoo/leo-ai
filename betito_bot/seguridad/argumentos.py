"""Validación de los argumentos que el modelo pasa a una tool, contra su esquema."""

from __future__ import annotations

from typing import Any

MAX_TEXTO = 2000


def _convertir(nombre: str, valor: Any, spec: dict) -> Any:
    tipo = spec.get("type")
    if tipo == "string":
        if not isinstance(valor, str):
            raise ValueError(f"{nombre} debe ser texto")
        if len(valor) > MAX_TEXTO:
            raise ValueError(f"{nombre} es demasiado largo (máximo {MAX_TEXTO} caracteres)")
    elif tipo in ("integer", "number"):
        if isinstance(valor, str):  # algunos modelos mandan "24" en vez de 24
            try:
                valor = float(valor)
            except ValueError:
                raise ValueError(f"{nombre} debe ser un número") from None
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor != valor or valor in (float("inf"), float("-inf")):
            raise ValueError(f"{nombre} debe ser un número")
        if tipo == "integer":
            if valor != int(valor):
                raise ValueError(f"{nombre} debe ser un número entero")
            valor = int(valor)
    elif tipo == "boolean":
        if not isinstance(valor, bool):
            raise ValueError(f"{nombre} debe ser verdadero o falso")
    if "enum" in spec and valor not in spec["enum"]:
        raise ValueError(f"{nombre} debe ser uno de: {', '.join(map(str, spec['enum']))}")
    return valor


def validar_argumentos(schema: dict, args: dict) -> dict:
    """Devuelve los argumentos ya convertidos; lanza ValueError si no cumplen el esquema.

    `schema` es la entrada de la tool en formato OpenAI. Rechaza parámetros que el
    esquema no declara: así el modelo no alcanza los que la función acepta pero no
    se le ofrecen.
    """
    parametros = schema["function"].get("parameters") or {}
    propiedades = parametros.get("properties") or {}
    if not isinstance(args, dict):
        raise ValueError("los argumentos deben ser un objeto")
    desconocidos = [k for k in args if k not in propiedades]
    if desconocidos:
        raise ValueError(f"parámetros no permitidos: {', '.join(desconocidos)}. Permitidos: {', '.join(propiedades) or 'ninguno'}")
    limpios = {k: _convertir(k, v, propiedades[k]) for k, v in args.items() if v is not None}
    faltantes = [k for k in parametros.get("required", []) if k not in limpios]
    if faltantes:
        raise ValueError(f"faltan parámetros obligatorios: {', '.join(faltantes)}")
    return limpios
