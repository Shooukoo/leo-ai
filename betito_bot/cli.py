"""Interfaz de consola: entrada con prompt_toolkit y salida con Rich.

La UI no conoce el bucle de los agentes: solo consume los `Evento` que emiten
(pensando, tool_call, tool_result) y muestra la respuesta final.
"""

import json
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from betito_bot.agents.eventos import Evento
from betito_bot.llm.groq_client import build_client
from betito_bot.orchestrator.router import AgenteDesconocido, Orchestrator

HISTORIAL_PATH = Path.home() / ".leo_ai_historial"
SALIDAS = ("exit", "salir")

COMANDOS = {
    "/ayuda": "Muestra comandos, agentes y atajos",
    "/agentes": "Lista los agentes disponibles",
    "/limpiar": "Borra la memoria de los agentes y la pantalla",
    "/salir": "Termina la sesión",
}


class LeoCompleter(Completer):
    """Autocompleta `/comandos` y `@agentes` al inicio del mensaje."""

    def __init__(self, agentes: dict[str, str]):
        self.agentes = agentes  # {nombre: descripcion}

    def get_completions(self, document, complete_event):
        texto = document.text_before_cursor
        if " " in texto:
            return
        if texto.startswith("/"):
            opciones = COMANDOS
        elif texto.startswith("@"):
            opciones = {f"@{nombre}": desc for nombre, desc in self.agentes.items()}
        else:
            return
        for opcion, desc in opciones.items():
            if opcion.startswith(texto):
                yield Completion(opcion, start_position=-len(texto), display_meta=desc)


def formatear_argumentos(crudos: str | None) -> str:
    """`{"cultivo": "Fresa"}` -> `cultivo="Fresa"`; si no es JSON válido lo deja tal cual."""
    try:
        args = json.loads(crudos or "{}")
    except json.JSONDecodeError:
        return crudos or ""
    if not isinstance(args, dict):
        return str(args)
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())


class Interfaz:
    def __init__(self, orchestrator: Orchestrator, console: Console | None = None):
        self.orchestrator = orchestrator
        self.console = console or Console(highlight=False)
        self.session = PromptSession(
            history=FileHistory(str(HISTORIAL_PATH)),
            completer=LeoCompleter({n: a.descripcion for n, a in orchestrator.agents.items()}),
            complete_while_typing=True,
            key_bindings=self._atajos(),
            bottom_toolbar=self._barra_estado,
            placeholder=HTML("<style fg='ansibrightblack'>Pregunta algo · /ayuda · @agente para elegir quién responde</style>"),
        )
        self._status = None

    @staticmethod
    def _atajos() -> KeyBindings:
        kb = KeyBindings()

        @kb.add("escape", "enter")  # Alt+Enter: la mayoría de terminales no distinguen Shift+Enter
        def _(event):
            event.current_buffer.insert_text("\n")

        return kb

    def _barra_estado(self):
        agente = self.orchestrator.ultimo_agente or self.orchestrator.default_agent
        modelo = getattr(agente, "model", "?")
        return HTML(
            f" agente: <b>{agente.name}</b>  ·  modelo: {modelo}  ·  "
            "Alt+Enter nueva línea  ·  Ctrl+D salir"
        )

    # --- salida ---------------------------------------------------------

    def bienvenida(self):
        self.console.print(
            Panel.fit(
                "[bold green]BETITO BOT[/] · monitoreo de invernadero\n"
                "[dim]Escribe tu pregunta. [cyan]/ayuda[/] para comandos, "
                "[cyan]@sensores[/] o [cyan]@monitoreo[/] para elegir agente.[/]",
                border_style="green",
            )
        )

    def ayuda(self):
        tabla = Table(show_header=False, box=None, padding=(0, 2))
        tabla.add_column(style="cyan")
        tabla.add_column()
        for comando, desc in COMANDOS.items():
            tabla.add_row(comando, desc)
        tabla.add_row("", "")
        for nombre, agente in self.orchestrator.agents.items():
            tabla.add_row(f"@{nombre}", agente.descripcion)
        tabla.add_row("", "")
        tabla.add_row("Tab", "Autocompletar comandos y agentes")
        tabla.add_row("Alt+Enter", "Salto de línea sin enviar")
        tabla.add_row("Ctrl+C", "Cancela la respuesta en curso")
        tabla.add_row("Ctrl+D", "Salir")
        self.console.print(Padding(tabla, (1, 2)))

    def agentes(self):
        tabla = Table(title="Agentes", title_justify="left", header_style="bold")
        tabla.add_column("Agente", style="cyan")
        tabla.add_column("Modelo", style="dim")
        tabla.add_column("Qué responde")
        for nombre, agente in self.orchestrator.agents.items():
            tabla.add_row(f"@{nombre}", getattr(agente, "model", ""), agente.descripcion)
        self.console.print(tabla)
        self.console.print(
            "[dim]Sin @mención, los mensajes sobre sensores, fallas, depósitos o "
            "variables (CO2, lux, pH, EC…) van a @sensores; el resto a @monitoreo.[/]"
        )

    def on_event(self, ev: Evento):
        if ev.tipo == "pensando":
            self._status.update(f"[bold]{ev.agente}[/] pensando…")
        elif ev.tipo == "tool_call":
            args = formatear_argumentos(ev.datos.get("argumentos"))
            self._status.update(f"[bold]{ev.agente}[/] consultando [cyan]{ev.datos['nombre']}[/]…")
            self.console.print(Text.assemble(("  ⎿ ", "dim"), (ev.datos["nombre"], "cyan"), (f"({args})", "dim")))
        elif ev.tipo == "tool_result" and ev.datos.get("error"):
            self.console.print(Text(f"    ✗ {ev.datos['error']}", style="red"))

    def responder(self, texto: str):
        try:
            with self.console.status("pensando…", spinner="dots") as status:
                self._status = status
                respuesta = self.orchestrator.handle(texto, on_event=self.on_event)
        except AgenteDesconocido as e:
            disponibles = ", ".join(f"@{n}" for n in self.orchestrator.agents)
            self.console.print(f"[yellow]No existe el agente @{e}.[/] Disponibles: {disponibles}")
            return
        except KeyboardInterrupt:
            self.console.print("[yellow]Respuesta cancelada.[/]")
            return
        except Exception as e:  # p. ej. Groq sin API key o sin red: avisar y seguir en la sesión
            self.console.print(Panel(f"{type(e).__name__}: {e}", title="Error", border_style="red", title_align="left"))
            return
        finally:
            self._status = None

        agente = self.orchestrator.ultimo_agente.name
        self.console.print(Text(f"● {agente}", style="bold green"))
        self.console.print(Padding(Text(respuesta.strip() or "(respuesta vacía)"), (0, 0, 1, 2)))

    # --- bucle ----------------------------------------------------------

    def ejecutar_comando(self, texto: str) -> bool:
        """Ejecuta un `/comando`. Devuelve False si la sesión debe terminar."""
        comando = texto.split()[0].lower()
        if comando == "/salir":
            return False
        if comando == "/ayuda":
            self.ayuda()
        elif comando == "/agentes":
            self.agentes()
        elif comando == "/limpiar":
            self.orchestrator.reset()
            self.orchestrator.ultimo_agente = None
            self.console.clear()
            self.bienvenida()
            self.console.print("[dim]Memoria de los agentes borrada.[/]")
        else:
            self.console.print(f"[yellow]Comando desconocido: {comando}.[/] Escribe /ayuda.")
        return True

    def run(self):
        self.bienvenida()
        while True:
            try:
                texto = self.session.prompt(HTML("<ansigreen><b>❯</b></ansigreen> ")).strip()
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            if not texto:
                continue
            if texto.lower() in SALIDAS:
                break
            if texto.startswith("/"):
                if not self.ejecutar_comando(texto):
                    break
                continue
            if texto.startswith("@") and " " not in texto:
                self.console.print(f"[yellow]Escribe la pregunta después de {texto}[/], p. ej. {texto} ¿cómo va la parcela 1?")
                continue
            self.responder(texto)
        self.console.print("[dim]Hasta luego.[/]")


def main():
    Interfaz(Orchestrator(build_client())).run()


if __name__ == "__main__":
    main()
