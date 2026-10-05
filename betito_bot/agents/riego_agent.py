from langchain_core.language_models import BaseChatModel

from betito_bot.agents.tool_agent import ToolAgent
from betito_bot.tools.riego_tools import RiegoTools

SYSTEM_PROMPT = """Eres el agente de análisis de riego de un invernadero inteligente.
Reglas:
- Responde SOLO con datos devueltos por las herramientas; si no los tienes, llámalas. Nunca inventes valores.
- No calcules ni reclasifiques nada: las duraciones, la frecuencia, la subida de humedad y el diagnóstico de cada ciclo ya vienen calculados. Usa el motivo que devuelve la herramienta.
- Diagnósticos posibles de un ciclo: ok, sobre_riego (la humedad pasó del máximo o se regó con el suelo ya húmedo), sin_efecto (se regó y la humedad casi no cambió), en_curso (sigue regando) y sin_datos (faltan lecturas de humedad).
- Un ciclo con nota de incompleto tiene duración no confiable: dilo en vez de usarla como válida.
- Si un sensor viene sin datos de riego, dilo claramente; no es lo mismo que "no se regó".
- Cita el sensor_id y la hora (UTC) de cada ciclo que menciones.
- Responde en español, breve y priorizando los problemas.

Formato de la respuesta (obligatorio):
- NUNCA pegues JSON ni nombres de campos crudos (como subida_pct); redáctalo como un reporte para una persona.
- La salida se lee en una terminal: texto plano, sin tablas ni negritas con asteriscos. Usa líneas que empiecen con "- " y emojis solo como indicador de estado (✅ OK, ⚠️ aviso, ❌ problema).
- Estructura: una línea de resumen (cuántos riegos hubo, cada cuánto y cuánto duran en promedio), luego los ciclos con problema, uno por viñeta, y al final una línea con lo que está bien.
- Cada viñeta de problema: hora de inicio como HH:MM UTC, duración, humedad antes y pico con su unidad, qué pasó en palabras simples y la acción recomendada si es evidente.

Ejemplo:
Resumen: 6 riegos en 24 h en la Cama 1 (suelo-cama1-7en1), uno cada 4 h, de 10 min en promedio.
- ❌ Riego de las 14:00 UTC (10 min): la humedad pasó de 70.1 % a 82.3 %, por encima del máximo de 75 %. Acortar el riego o espaciarlo.
- ⚠️ Riego de las 18:00 UTC (10 min): la humedad solo cambió 0.4 puntos. Revisar bomba, válvula y goteros.
Sin problemas: los otros 4 riegos subieron la humedad unos 12 puntos."""

_OBJ = "object"
_FILTROS = {
    "horas": {"type": "number", "description": "Horas hacia atrás a analizar (default 24, máximo 168)."},
    "parcela": {"type": "string", "description": "Nombre de la parcela, p. ej. Parcela 1."},
    "cultivo": {"type": "string", "description": "Nombre del cultivo, p. ej. Fresa."},
}
TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "resumen_riego",
        "description": "Resumen del riego por sensor de suelo: número de ciclos, duración media, cada cuánto se riega, "
                       "subida media de humedad y lista de ciclos con sobre-riego o sin efecto.",
        "parameters": {"type": _OBJ, "properties": _FILTROS}}},
    {"type": "function", "function": {
        "name": "ciclos_riego",
        "description": "Detalle de cada ciclo de riego reconstruido: inicio, fin, duración, humedad de suelo antes, "
                       "pico después, cuánto subió y diagnóstico.",
        "parameters": {"type": _OBJ, "properties": {**_FILTROS, "sensor_id": {"type": "string"}}}}},
]


class RiegoAgent(ToolAgent):
    name = "riego"
    descripcion = "Análisis de riego: ciclos (duración y frecuencia), subida de humedad de suelo, sobre-riego y riegos sin efecto."

    def __init__(self, client: BaseChatModel, tools: RiegoTools | None = None):
        self.tools = tools or RiegoTools()
        super().__init__(
            client,
            system_prompt=SYSTEM_PROMPT,
            tools_schema=TOOLS_SCHEMA,
            registry={
                "resumen_riego": self.tools.resumen_riego,
                "ciclos_riego": self.tools.ciclos_riego,
            },
        )
