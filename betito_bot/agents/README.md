# Agentes dedicados en Markdown

Además de los agentes en Python (`*_agent.py`), cada archivo `<nombre>.md` de esta carpeta define un agente que se invoca con `@nombre tarea…`. El agente por defecto también puede pasarle trabajo con la tool `delegate(agent, task)`.

```markdown
---
name: nombre            # opcional; si falta se usa el nombre del archivo (solo letras, números y _)
description: Qué responde, en una línea
tools: [ultimo_estado, historial]   # tools permitidas
model: openai/gpt-oss-20b           # opcional; por defecto LLM_MODEL
---
Prompt de sistema del agente.
```

- `tools` solo puede nombrar tools que ya existan en los agentes de Python (`estado_sensores`, `ultimo_estado`, `historial`, `nivel_depositos`, `calcular_dpv`, `riesgo_botrytis`, `resumen_riego`, `ciclos_riego`, `get_ultimas_lecturas`, `delegate` y `usar_skill`). Si nombra una que no existe, el agente no se carga y la consola muestra un aviso al arrancar.
- No se puede usar el nombre de un agente que ya existe (`monitoreo`, `sensores`, `riego`).
- A todo prompt de sistema se le añaden las reglas comunes de alcance (`betito_bot/seguridad/reglas.py`): no hace falta repetirlas ni se pueden quitar desde el `.md`.
- Los cambios se aplican al reiniciar la consola.
