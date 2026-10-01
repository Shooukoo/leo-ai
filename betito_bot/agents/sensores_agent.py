from groq import Groq

from betito_bot.agents.tool_agent import ToolAgent
from betito_bot.tools.sensores_tools import SensoresTools

SYSTEM_PROMPT = """Eres el agente de salud de sensores de un invernadero inteligente.
Reglas:
- Responde SOLO con datos devueltos por las herramientas; si no los tienes, llámalas. Nunca inventes valores.
- Cita siempre el sensor_id y la hora (UTC) de cada lectura que menciones.
- Si una lectura está obsoleta, tiene avisos o fallas, dilo explícitamente en vez de usar el dato como válido.
- Valores de error conocidos: 85.0 y -127 en el DS18B20, lux 65535 = saturado, pH 14 = fuera de rango.
- La EC y el NPK del sensor de suelo 7 en 1 son del suelo/sustrato: no los compares con los umbrales de la solución nutritiva y trata el NPK como indicativo, no absoluto.
- Si no existe sensor para lo que se pregunta (p. ej. EC o pH de la solución nutritiva), dilo claramente.
- Responde en español, breve y priorizando los problemas."""

_OBJ = "object"
TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "estado_sensores",
        "description": "Diagnóstico de todos los sensores: sin reportar, valores fuera de rango o de error, lecturas planas (trabado) y discrepancias entre SHT31 de la misma zona.",
        "parameters": {"type": _OBJ, "properties": {
            "obsoleto_min": {"type": "integer", "description": "Minutos sin lectura para considerar un sensor sin reportar (default 10)."},
        }}}},
    {"type": "function", "function": {
        "name": "ultimo_estado",
        "description": "Última lectura de cada sensor asociado a un cultivo o parcela (incluye los sensores ambientales compartidos), con avisos y marca de obsoleta.",
        "parameters": {"type": _OBJ, "properties": {
            "cultivo": {"type": "string", "description": "Nombre del cultivo, p. ej. Fresa."},
            "parcela": {"type": "string", "description": "Nombre de la parcela, p. ej. Parcela 1."},
            "obsoleto_min": {"type": "integer", "description": "Minutos tras los cuales una lectura es obsoleta (default 10)."},
        }}}},
    {"type": "function", "function": {
        "name": "historial",
        "description": "Promedio, mínimo y máximo de una variable por hora o por día.",
        "parameters": {"type": _OBJ, "properties": {
            "variable": {"type": "string", "description": "Campo, p. ej. temperatura_c, humedad_aire_pct, co2_ppm, lux, ph_suelo."},
            "horas": {"type": "integer", "description": "Horas hacia atrás (default 24)."},
            "ventana": {"type": "string", "enum": ["hora", "dia"]},
            "sensor_id": {"type": "string"},
            "parcela": {"type": "string"},
        }, "required": ["variable"]}}},
    {"type": "function", "function": {
        "name": "nivel_depositos",
        "description": "Nivel en % y cm de cada depósito y tendencia de consumo (%/hora y horas hasta vaciarse).",
        "parameters": {"type": _OBJ, "properties": {}}}},
    {"type": "function", "function": {
        "name": "calcular_dpv",
        "description": "Déficit de presión de vapor (kPa) a partir de temperatura y humedad relativa del aire.",
        "parameters": {"type": _OBJ, "properties": {
            "temp_c": {"type": "number"}, "hr_pct": {"type": "number"},
        }, "required": ["temp_c", "hr_pct"]}}},
    {"type": "function", "function": {
        "name": "riesgo_botrytis",
        "description": "Riesgo de botrytis (bajo/medio/alto) a partir de temperatura y humedad relativa.",
        "parameters": {"type": _OBJ, "properties": {
            "temp_c": {"type": "number"}, "hr_pct": {"type": "number"},
        }, "required": ["temp_c", "hr_pct"]}}},
]


class SensoresAgent(ToolAgent):
    name = "sensores"

    def __init__(self, client: Groq, tools: SensoresTools | None = None):
        self.tools = tools or SensoresTools()
        super().__init__(
            client,
            system_prompt=SYSTEM_PROMPT,
            tools_schema=TOOLS_SCHEMA,
            registry={
                "estado_sensores": self.tools.estado_sensores,
                "ultimo_estado": self.tools.ultimo_estado,
                "historial": self.tools.historial,
                "nivel_depositos": self.tools.nivel_depositos,
                "calcular_dpv": self.tools.calcular_dpv,
                "riesgo_botrytis": self.tools.riesgo_botrytis,
            },
        )
