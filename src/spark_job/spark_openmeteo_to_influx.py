#!/usr/bin/env python3
"""
Spark Streaming: Kafka vers InfluxDB
Version optimisée pour 3 villes
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import requests
import json
import os

# Configuration InfluxDB
INFLUX_URL = "http://localhost:8086"
INFLUX_ORG = "admin"  # Remplacez par votre organisation
INFLUX_BUCKET = "open_meteo_metrics"
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "Q1WGllJC-OyfggL3RuQ-uwVQho0K5WAmWDr2t9ArJOGj2FFKxPDxkI-Jh36FjHFX8LxYF547VvAYdMA8lDAyBA==")  # Remplacez

# Créer SparkSession
spark = SparkSession.builder \
    .appName("WeatherToInfluxOptimized") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
    .config("spark.sql.shuffle.partitions", "10") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# Schema pour parser le JSON
schema = StructType([
    StructField("source", StringType()),
    StructField("city", StringType()),
    StructField("timestamp", StringType()),
    StructField("weather", StructType([
        StructField("temperature", DoubleType()),
        StructField("windspeed", DoubleType()),
        StructField("winddirection", DoubleType()),
        StructField("weathercode", IntegerType()),
        StructField("is_day", IntegerType())
    ]))
])

print("📡 Connexion à Kafka...")

# Lire depuis Kafka
df = spark \
    .readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "10.0.0.111:9092,10.0.0.102:9092,10.0.0.103:9092") \
    .option("subscribe", "open-meteo-weather") \
    .option("startingOffsets", "latest") \
    .option("maxOffsetsPerTrigger", "100") \
    .load()

# Parser le JSON
weather_df = df.select(
    col("timestamp").alias("kafka_timestamp"),
    from_json(col("value").cast("string"), schema).alias("data")
).select(
    col("kafka_timestamp"),
    col("data.city"),
    col("data.timestamp"),
    col("data.weather.temperature"),
    col("data.weather.windspeed"),
    col("data.weather.weathercode")
)

# Fonction pour écrire dans InfluxDB
def write_to_influx(batch_df, batch_id):
    print(f"📊 Batch {batch_id}: {batch_df.count()} enregistrements")
    
    rows = batch_df.collect()
    
    for row in rows:
        try:
            # Format InfluxDB Line Protocol
            data = f"weather,city={row.city} "
            data += f"temperature={row.temperature},"
            data += f"windspeed={row.windspeed},"
            data += f"weathercode={row.weathercode if row.weathercode else 0}"
            
            # Envoyer vers InfluxDB
            response = requests.post(
                f"{INFLUX_URL}/api/v2/write",
                params={
                    "org": INFLUX_ORG,
                    "bucket": INFLUX_BUCKET,
                    "precision": "s"
                },
                headers={
                    "Authorization": f"Token {INFLUX_TOKEN}",
                    "Content-Type": "text/plain; charset=utf-8"
                },
                data=data
            )
            
            if response.status_code == 204:
                print(f"✅ {row.city}: Temp={row.temperature}°C, Wind={row.windspeed}km/h")
            else:
                print(f"❌ Erreur InfluxDB: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Erreur: {e}")

# Agrégation par fenêtre (optionnel)
aggregated_df = weather_df \
    .withWatermark("kafka_timestamp", "2 minutes") \
    .groupBy(
        window(col("kafka_timestamp"), "1 minute"),
        col("city")
    ) \
    .agg(
        avg("temperature").alias("avg_temp"),
        avg("windspeed").alias("avg_wind")
    )

# Écrire vers InfluxDB
query = weather_df.writeStream \
    .foreachBatch(write_to_influx) \
    .outputMode("append") \
    .trigger(processingTime="30 seconds") \
    .option("checkpointLocation", "/tmp/checkpoint-weather") \
    .start()

print("✅ Streaming démarré! Appuyez sur Ctrl+C pour arrêter...")
query.awaitTermination()
