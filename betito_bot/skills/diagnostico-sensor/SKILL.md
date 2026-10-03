---
name: diagnostico-sensor
description: Diagnóstico paso a paso de un sensor concreto y qué revisar en campo
---
Diagnostica el sensor que indique el usuario (por sensor_id, parcela o variable). Si no dice cuál, llama a `estado_sensores` y elige el que tenga el problema más grave.

Pasos:
1. Llama a `ultimo_estado` con la parcela o el cultivo del sensor para ver su última lectura y sus avisos.
2. Llama a `historial` de la variable afectada para ese `sensor_id`, por hora, en las últimas 24 horas.
3. Interpreta el patrón:
   - Valor plano por horas: sensor trabado o desconectado.
   - 85.0 o -127 en un DS18B20: error de lectura del sensor, no una temperatura real.
   - Lux 65535: sensor saturado (luz directa o mal orientado).
   - Sin reportar: alimentación, cableado o red.
   - Dos SHT31 de la misma zona que no coinciden: uno está descalibrado.

Responde con:
- Qué le pasa al sensor, en una frase.
- La evidencia: valores y horas (UTC).
- Una lista corta de qué revisar en campo, en orden.
