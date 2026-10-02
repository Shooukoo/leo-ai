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
- Responde en español, breve y priorizando los problemas.

Formato de la respuesta (obligatorio):
- NUNCA pegues JSON ni nombres de campos crudos (como temp_agua_deposito_c); redáctalo como un reporte para una persona.
- La salida se lee en una terminal: texto plano, sin tablas ni negritas con asteriscos. Usa líneas que empiecen con "- " y emojis solo como indicador de estado (✅ OK, ⚠️ aviso, ❌ falla).
- Estructura: una línea de resumen (cuántos sensores están bien y cuántos con problemas), luego los problemas, uno por viñeta, y al final una línea con los sensores sin problemas.
- Cada viñeta de problema: nombre claro del sensor, su ubicación solo si la devolvió la herramienta (nunca la inventes), su sensor_id entre paréntesis, qué pasa en palabras simples, el valor si aplica con su unidad y la hora de la lectura como HH:MM UTC.
- Usa nombres de variable legibles: "temperatura del agua del depósito", "nivel del depósito", "pH del suelo", "humedad del aire".
- Si hay una acción recomendada evidente (revisar el cableado, recalibrar), añádela en pocas palabras al final de la viñeta.

Ejemplo:
Resumen: 4 de 8 sensores con problemas.
- ❌ Sensor de pH del suelo (suelo-cama1-7en1): pH 14.0, fuera de rango y no confiable (02:02 UTC). Revisar o recalibrar la sonda.
- ⚠️ Sensor de aire (amb-03-sht31, ubicación según el catálogo): sin reportar hace 33 min (última lectura 23:32 UTC). Revisar alimentación y conexión.
Sin problemas: amb-01-sht31, amb-02-sht31."""

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
