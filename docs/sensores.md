# Sensores seleccionados y arranque del agente de sensores

Resumen de la investigación de respaldo del Invernadero Inteligente (lista de compra `sensores.pdf`, precios de referencia del 08–11/09/2026; no se ha realizado ninguna compra).

## Sensores

| Sensor | Variable | Cant. | Interfaz | Notas |
|---|---|---|---|---|
| SHT31 | Temp. y humedad del aire | 24 | I2C 0x44/0x45 | ±0.3 °C, ±2 %HR. Solo 2 por bus I2C. |
| SCD40 | CO2 | 4 | I2C 0x62 | 400–2,000 ppm, ±(50 ppm + 5 %). Calibración automática asume ~400 ppm semanal. |
| BH1750 | Lux | 10 | I2C 0x23/0x5C | Satura en 65,535 lux. No mide PAR/PPFD. |
| Gemho 7 en 1 | Suelo: humedad, temp, EC, pH, NPK | 2 | RS485 Modbus-RTU | Mapa de registros por confirmar. EC de **suelo**, no de solución. |
| DS18B20 | Temp. del agua | 2 | 1-Wire | 85.0 = arranque, -127 = desconectado. |
| A02YYUW | Nivel del depósito | 5 | UART 9600 | 3–450 cm, zona ciega 3 cm. |
| TDS / kit pH | EC y pH del agua | 2 / 2 | Analógico | Referencia / excluido. |

## Hallazgos a resolver antes de comprar

1. No hay sensor confirmado de EC y pH de la **solución nutritiva** (el "kit combinado RS485" no figura como renglón).
2. El total de $6,391.37 incluye ítems excluidos/referencia ($785.74); faltan ESP32, conversor TTL↔RS485, fuente 12–24 V, pull-ups, cajas y cableado.
3. Sensor 7 en 1: la hoja de datos consultada es de un modelo genérico equivalente (JXBS-3001-NPK-RS). Con dos sondas hay que cambiar la dirección Modbus de una. Debe calibrarse contra una referencia; NPK es indicativo.
4. SHT31 ×24: sin multiplexor I2C hay que repartirlos entre ESP32; decidir cuántos puntos reales de medición habrá.
5. SCD40 vs SCD41 (rango 5,000 ppm y single-shot); revisar si la calibración automática aplica en invernadero cerrado.
6. BH1750 saturado ≈ sol directo bajo film; tratar 65,535 como "saturado".
7. A02YYUW: montar fuera del agua, >3 cm del nivel máximo; registrar la geometría del depósito.
8. DS18B20: 85.0 y -127 son errores, no temperaturas.

## Esquema de datos

Colección `lecturas_sensores`: obligatorios `_id`, `fecha_hora`, `sensor_id`, `parcela`; el resto opcional (`co2_ppm`, `lux`, `temp_suelo_c`, `ec_suelo_us_cm`, `ph_suelo`, `n/p/k_mg_kg`, `temp_agua_deposito_c`, `temp_agua_retorno_c`, `nivel_deposito_cm`, `nivel_deposito_pct`, `ec_solucion_ms_cm`, `ph_solucion`, `fallas`), numéricos como `number`. Colección `sensores` (catálogo): `sensor_id`, `modelo`, `variables`, `parcela`, `cultivo`, `ubicacion`, `rango_valido`, `fecha_instalacion`, `ultima_calibracion`, `activo`. Índices `{sensor_id, fecha_hora}` y `{parcela, fecha_hora}`. `sensor_id` legible: `amb-01-sht31`, `suelo-cama1-7en1`, `dep-a-nivel`. Publicar promedios de 1 minuto.

## Rangos de validación

Implementados en `betito_bot/sensores/validacion.py`: temperatura aire 0–60 °C, HR 0–100 %, CO2 300–2,000 ppm, lux 65,535 = saturado y 0 de día = tapado, pH suelo 3–9, EC suelo <10,000 µS/cm, NPK <1,999 mg/kg, DS18B20 85.0/-127 = error, distancia A02YYUW 3–450 cm, valor plano por horas = sensor trabado, diferencia entre SHT31 de la misma zona > umbral.

## Plan de arranque

0. Contrato de datos (esquema + catálogo). **Hecho.**
1. Datos simulados con fallas inyectadas. **Hecho** (`betito_bot/sensores/simulador.py`).
2. Herramientas de lectura fijas. **Hecho** (`betito_bot/tools/sensores_tools.py`).
3. Reglas del agente (prompt). **Hecho.**
4. Seguridad: usuario Mongo de solo lectura para el agente, credenciales por variable de entorno. **Pendiente.**
5. Pruebas con fallas. **Hecho** (`tests/`).
6. Hardware real por etapas: nodo ambiente (SHT31 + BH1750 + SCD40), nodo de depósitos (A02YYUW + DS18B20), sensor de suelo RS485. **Pendiente.**

## Vacíos

- Decidir el sensor de EC y pH de la solución nutritiva.
- Confirmar hojas de datos del DS18B20, la trama del A02YYUW y el mapa de registros real del Gemho.
- Definir cuántos puntos de medición de aire habrá y cómo se reparten entre ESP32.
- Sin validación de sondas 7 en 1 en fibra de coco o tezontle: calibración propia.
- Conectividad del predio (condiciona si los nodos necesitan buffer local).

## Fuentes

Lista `sensores.pdf`; datasheets de Sensirion SCD4x, Adafruit SHT31-D, BH1750, DFRobot A02YYUW (SEN0311) y manual 7 en 1 JXBS-3001-NPK-RS.
