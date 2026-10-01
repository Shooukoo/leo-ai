// Crea la colección LEO_AI aplicando el mismo $jsonSchema exportado desde
// MongoDB Atlas, y carga una lectura de ejemplo para poder probar el
// agente localmente sin depender de Atlas.

db = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE || "LEO_AI");

db.createCollection("LEO_AI", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "cultivo",
        "fecha_hora",
        "humedad_aire_pct",
        "humedad_suelo_pct",
        "parcela",
        "riego_activo",
        "sensor_id",
        "temperatura_c"
      ],
      properties: {
        _id: { bsonType: "objectId" },
        cultivo: { bsonType: "string" },
        fecha_hora: { bsonType: "date" },
        humedad_aire_pct: { bsonType: "int" },
        humedad_suelo_pct: { bsonType: "int" },
        observacion: { bsonType: "string" },
        parcela: { bsonType: "string" },
        riego_activo: { bsonType: "bool" },
        sensor_id: { bsonType: "string" },
        temperatura_c: { bsonType: "double" }
      }
    }
  }
});

db.LEO_AI.insertOne({
  cultivo: "Tomate",
  fecha_hora: new Date(),
  humedad_aire_pct: 55,
  humedad_suelo_pct: 48,
  observacion: "Lectura de ejemplo cargada por init-mongo.js",
  parcela: "Parcela 1",
  riego_activo: false,
  sensor_id: "sensor-demo-1",
  temperatura_c: 24.5
});

// ---------------------------------------------------------------------------
// Agente de sensores: lecturas multi-sensor y catálogo.
// Cada nodo publica solo las variables que mide, por eso solo _id,
// fecha_hora, sensor_id y parcela son obligatorios. Los valores numéricos
// usan "number" (SHT31 y sondas entregan decimales).
// ---------------------------------------------------------------------------
const num = { bsonType: "number" };

db.createCollection("lecturas_sensores", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "fecha_hora", "sensor_id", "parcela"],
      properties: {
        _id: { bsonType: "objectId" },
        fecha_hora: { bsonType: "date" },
        sensor_id: { bsonType: "string" },
        parcela: { bsonType: "string" },
        cultivo: { bsonType: "string" },
        temperatura_c: num,
        humedad_aire_pct: num,
        humedad_suelo_pct: num,
        riego_activo: { bsonType: "bool" },
        co2_ppm: num,
        lux: num,
        temp_suelo_c: num,
        ec_suelo_us_cm: num,
        ph_suelo: num,
        n_mg_kg: num,
        p_mg_kg: num,
        k_mg_kg: num,
        temp_agua_deposito_c: num,
        temp_agua_retorno_c: num,
        nivel_deposito_cm: num,
        nivel_deposito_pct: num,
        ec_solucion_ms_cm: num,
        ph_solucion: num,
        fallas: { bsonType: "array", items: { bsonType: "string" } }
      }
    }
  }
});
db.lecturas_sensores.createIndex({ sensor_id: 1, fecha_hora: -1 });
db.lecturas_sensores.createIndex({ parcela: 1, fecha_hora: -1 });

db.createCollection("sensores");
db.sensores.createIndex({ sensor_id: 1 }, { unique: true });
// El catálogo se siembra con: python -m betito_bot.sensores.simulador
