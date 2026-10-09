import re
from contextvars import ContextVar
from typing import Callable

from langchain_core.language_models import BaseChatModel

from betito_bot.agents.base import BaseAgent
from betito_bot.agents.diagnostico_agent import DiagnosticoAgent
from betito_bot.agents.eventos import Evento, OnEvento
from betito_bot.agents.monitoreo_agent import MonitoreoAgent
from betito_bot.agents.riego_agent import RiegoAgent
from betito_bot.agents.sensores_agent import SensoresAgent
from betito_bot.memory.sesion import SESION, SESION_POR_DEFECTO
from betito_bot.seguridad.guardian import Guardian, normalizar as _normalizar
from betito_bot.seguridad.reglas import MAX_MENSAJE, RECHAZO

# Palabras clave que indican una pregunta sobre el estado/salud de los sensores.
SENSORES_PATRON = re.compile(
    r"\b(sensor\w*|falla\w*|calibr\w*|offline|obsolet\w*|trabad\w*|deposito\w*|nivel\w*|"
    r"co2|lux|ph|ec|dpv|botrytis|sin reportar|no reporta\w*)\b"
)


# Preguntas sobre el riego. Se compara antes que SENSORES_PATRON: una pregunta de riego
# suele mencionar también "sensor" o "nivel".
RIEGO_PATRON = re.compile(r"\b(rieg\w*|sobrerieg\w*|regar\w*|rego|regaron|regando|regamos|regad\w*|irriga\w*)\b")
DIAGNOSTICO_PATRON = re.compile(r"\b(semaforo\w*|diagnostico de (estado|cultivos?|los cultivos))\b")

# `@nombre resto del mensaje` fuerza el agente sin pasar por el ruteo.
MENCION_PATRON = re.compile(r"^@(\w+)\s*(.*)$", re.DOTALL)


# Máximo de agentes encadenados con `delegate` (A delega en B, B en C...).
MAX_PROFUNDIDAD_DELEGACION = 3

# Callback de eventos y cadena de agentes de la ejecución en curso. Son ContextVar
# porque cada ejecución corre en su propio hilo (asyncio.to_thread copia el contexto)
# y `delegate` se llama como tool, sin acceso directo al `on_event` del agente.
_ON_EVENT: ContextVar[OnEvento | None] = ContextVar("on_event", default=None)
_CADENA: ContextVar[tuple[str, ...]] = ContextVar("cadena", default=())


class AgenteDesconocido(ValueError):
    pass


class Orchestrator:
    """Punto único de entrada; enruta cada mensaje al agente correspondiente.

    Ruteo por palabras clave: preguntas sobre riego van a `riego`; sobre sensores,
    fallas, depósitos o variables como CO2/lux/pH/EC van a `sensores`; el resto
    a `monitoreo`.
    Un mensaje que empieza con `@nombre` va directo a ese agente.
    peticiones de semáforo o diagnóstico de estado van a diagnostico

    Con `guardian`, cada mensaje se revisa antes de llegar al agente; sin él no
    hay revisión de entrada (las pruebas y el modo falso lo omiten).
    """

    def __init__(self, client: BaseChatModel, skills: dict | None = None, guardian: Guardian | None = None):
        self.guardian = guardian
        self.default_agent = MonitoreoAgent(client)
        self.agents: dict[str, BaseAgent] = {
            self.default_agent.name: self.default_agent,
            "sensores": SensoresAgent(client),
            "riego": RiegoAgent(client),
            "diagnostico": DiagnosticoAgent(client),
        }
        self.skills = skills or {}  # {nombre: Skill}; ver betito_bot/core/skills.py
        self.ultimo_agente: BaseAgent | None = None
        self._schema_base = list(self.default_agent.tools_schema)
        self._inyectar_herramientas()

    def registrar(self, agente: BaseAgent) -> None:
        """Agrega un agente (p. ej. uno definido en `betito_bot/agents/<nombre>.md`)."""
        self.agents[agente.name] = agente
        self._inyectar_herramientas()

    def catalogo_tools(self) -> dict[str, tuple[dict, Callable[..., dict]]]:
        """`{nombre: (esquema, función)}` con las tools de todos los agentes registrados."""
        catalogo = {}
        for agente in self.agents.values():
            registro = getattr(agente, "registry", {})
            for schema in getattr(agente, "tools_schema", []):
                nombre = schema["function"]["name"]
                if nombre in registro:
                    catalogo.setdefault(nombre, (schema, registro[nombre]))
        return catalogo

    def _inyectar_herramientas(self) -> None:
        """Da al agente por defecto `delegate` y, si hay skills, `usar_skill`."""
        otros = ", ".join(f"{n} ({a.descripcion})" for n, a in self.agents.items() if a is not self.default_agent)
        schema = self._schema_base + [{"type": "function", "function": {
            "name": "delegate",
            "description": f"Delega una tarea a un agente especializado y devuelve su respuesta. Agentes: {otros}.",
            "parameters": {"type": "object", "properties": {
                "agent": {"type": "string", "description": "Nombre del agente."},
                "task": {"type": "string", "description": "Tarea completa y autocontenida para el agente."},
            }, "required": ["agent", "task"]}}}]
        registro = {"delegate": self.delegate}
        if self.skills:
            lista = "; ".join(f"{s.name}: {s.description}" for s in self.skills.values())
            schema.append({"type": "function", "function": {
                "name": "usar_skill",
                "description": f"Lee las instrucciones completas de una skill antes de aplicarla. Skills: {lista}.",
                "parameters": {"type": "object", "properties": {
                    "nombre": {"type": "string", "description": "Nombre de la skill."},
                }, "required": ["nombre"]}}})
            registro["usar_skill"] = self.usar_skill
        self.default_agent.tools_schema = schema
        self.default_agent.registry = {**self.default_agent.registry, **registro}

    def delegate(self, agent: str, task: str) -> dict:
        """Tool: pasa `task` a otro agente y devuelve su respuesta, avisando inicio y fin."""
        nombre = agent.lstrip("@").lower()
        destino = self.agents.get(nombre)
        if destino is None:
            return {"error": f"No existe el agente {agent}. Disponibles: {', '.join(self.agents)}"}
        cadena = _CADENA.get()
        if nombre in cadena:
            return {"error": f"El agente {nombre} ya participa en esta consulta; responde tú mismo."}
        if len(cadena) >= MAX_PROFUNDIDAD_DELEGACION:
            return {"error": "Demasiadas delegaciones encadenadas; responde con lo que tienes."}
        on_event = _ON_EVENT.get()
        if on_event is not None:
            on_event(Evento("agente_inicio", nombre, {"tarea": task}))
        token = _CADENA.set(cadena + (nombre,))
        ok = False
        try:
            respuesta = destino.respond(task, on_event)
            ok = True
        finally:
            _CADENA.reset(token)
            if on_event is not None:
                on_event(Evento("agente_fin", nombre, {"ok": ok}))
        return {"agente": nombre, "respuesta": respuesta}

    def usar_skill(self, nombre: str) -> dict:
        """Tool: devuelve el cuerpo de una skill (se lee del disco solo al pedirla)."""
        skill = self.skills.get(nombre.lstrip("/"))
        if skill is None:
            return {"error": f"No existe la skill {nombre}. Disponibles: {', '.join(self.skills)}"}
        return {"skill": skill.name, "instrucciones": skill.leer()}

    def route(self, user_text: str) -> BaseAgent:
        texto = _normalizar(user_text)
        if RIEGO_PATRON.search(texto):
            return self.agents["riego"]
        if DIAGNOSTICO_PATRON.search(texto):
            return self.agents["diagnostico"]
        if SENSORES_PATRON.search(texto):
            return self.agents["sensores"]
        return self.default_agent

    def resolver(self, user_text: str) -> tuple[BaseAgent, str]:
        """Devuelve el agente que debe responder y el texto que recibe."""
        mencion = MENCION_PATRON.match(user_text.strip())
        if mencion is None:
            return self.route(user_text), user_text
        nombre, texto = mencion.groups()
        if nombre.lower() not in self.agents:
            raise AgenteDesconocido(nombre)
        return self.agents[nombre.lower()], texto

    def _bloqueo(self, texto_usuario: str) -> str | None:
        """Motivo por el que el mensaje no debe llegar a los agentes, o None."""
        if len(texto_usuario) > MAX_MENSAJE:
            return f"el mensaje supera los {MAX_MENSAJE} caracteres"
        if self.guardian is None:
            return None
        veredicto = self.guardian.revisar_entrada(texto_usuario)
        return None if veredicto.permitido else veredicto.motivo

    def handle(self, user_text: str, on_event: OnEvento | None = None,
               sesion: str = SESION_POR_DEFECTO, texto_usuario: str | None = None) -> str:
        """Atiende un mensaje en la sesión dada.

        `texto_usuario` es la parte que escribió la persona cuando `user_text` trae
        además texto de confianza (las instrucciones de una skill); es lo que se revisa.
        """
        agente, texto = self.resolver(user_text)
        self.ultimo_agente = agente
        motivo = self._bloqueo(texto if texto_usuario is None else texto_usuario)
        if motivo is not None:
            if on_event is not None:
                on_event(Evento("bloqueado", agente.name, {"etapa": "entrada", "motivo": motivo}))
            return RECHAZO
        t_evento, t_cadena, t_sesion = _ON_EVENT.set(on_event), _CADENA.set((agente.name,)), SESION.set(sesion)
        try:
            return agente.respond(texto, on_event)
        finally:
            _ON_EVENT.reset(t_evento)
            _CADENA.reset(t_cadena)
            SESION.reset(t_sesion)

    def reset(self, sesion: str | None = None) -> None:
        """Borra la memoria de una sesión o, sin `sesion`, la de todas."""
        if sesion is None:
            for agente in self.agents.values():
                agente.reset(todas=True)
            return
        token = SESION.set(sesion)
        try:
            for agente in self.agents.values():
                agente.reset()
        finally:
            SESION.reset(token)
