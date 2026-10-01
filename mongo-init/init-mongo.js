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
