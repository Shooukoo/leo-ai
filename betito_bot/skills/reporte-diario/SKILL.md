---
name: reporte-diario
description: Reporte del día del invernadero (sensores, depósitos, clima y riesgo de botrytis)
---
Arma el reporte diario del invernadero usando solo datos de las herramientas.

Pasos:
1. Llama a `estado_sensores` para saber qué sensores tienen problemas.
2. Llama a `nivel_depositos` para el nivel y las horas estimadas hasta vaciarse.
3. Llama a `historial` con `variable="temperatura_c"` y `ventana="hora"` (24 horas) y luego con `variable="humedad_aire_pct"`.
4. Con la temperatura y humedad más recientes, llama a `riesgo_botrytis` y a `calcular_dpv`.

Formato:
- Una línea de resumen general (✅ todo bien / ⚠️ hay avisos / ❌ hay fallas).
- Sección "Sensores": solo los que tienen problemas, con su sensor_id.
- Sección "Depósitos": nivel en % y horas hasta vaciarse.
- Sección "Clima": mínimo y máximo de temperatura y humedad de las últimas 24 h, DPV actual y riesgo de botrytis.
- Cierra con hasta 3 acciones recomendadas, ordenadas por urgencia.
