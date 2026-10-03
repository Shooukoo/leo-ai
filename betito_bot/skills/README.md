# Skills

Una skill es un conjunto de instrucciones reutilizable que se invoca desde la consola con `/nombre [@agente] petición`.

## Crear una

1. Crea `betito_bot/skills/<nombre>/SKILL.md`.
2. Arriba pon el frontmatter con `name` (lo que se escribe después de `/`) y `description` (una línea que se muestra en el autocompletado):

   ```markdown
   ---
   name: mi-skill
   description: Qué hace, en una línea
   ---
   Instrucciones para el agente: qué herramientas llamar, en qué orden y con qué formato responder.
   ```

3. Reinicia la consola. La skill aparece en `/skills` y al escribir `/`.

## Cómo se usa

- Al arrancar solo se lee el frontmatter. El cuerpo se lee cuando alguien invoca la skill.
- `/mi-skill parcela 1` manda las instrucciones y la petición al agente que elija el ruteo. Con `/mi-skill @sensores parcela 1` va directo a ese agente.
- El agente por defecto (`@monitoreo`) ve el nombre y la descripción de cada skill. Puede leer una por su cuenta con la tool `usar_skill`.
- En el frontmatter solo se admite YAML simple: `clave: valor`, listas `[a, b]` o listas con `- item`.
