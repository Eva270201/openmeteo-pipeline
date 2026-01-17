from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, to_timestamp, window, avg, round
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType

KAFKA_BOOTSTRAP = "10.0.0.111:9092,10.0.0.102:9092,10.0.0.103:9092"
TOPIC = "open-meteo-weather"

schema = StructType([
    StructField("source", StringType(), True),
    StructField("city", StringType(), True),
    StructField("timestamp", StringType(), True),
    StructField("weather", StructType([
        StructField("time", StringType(), True),
        StructField("interval", IntegerType(), True),
        StructField("temperature", DoubleType(), True),
        StructField("windspeed", DoubleType(), True),
        StructField("winddirection", IntegerType(), True),
        StructField("is_day", IntegerType(), True),
        StructField("weathercode", IntegerType(), True),
    ]), True),
])

spark = (
    SparkSession.builder
    .appName("OpenMeteoKafkaStreaming")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")


raw = (spark.readStream
      .format("kafka")
      .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
      .option("subscribe", TOPIC)
      .option("startingOffsets", "latest")
      .load())


parsed = (raw.selectExpr("CAST(value AS STRING) as json_str")
          .select(from_json(col("json_str"), schema).alias("data"))
          .select(
              col("data.city").alias("city"),
              to_timestamp(col("data.timestamp")).alias("event_ts"),
              col("data.weather.temperature").alias("temperature"),
              col("data.weather.windspeed").alias("windspeed")
          )
          .where(col("event_ts").isNotNull())
         )


agg = (parsed
       .withWatermark("event_ts", "2 minutes")
       .groupBy(window(col("event_ts"), "1 minute"), col("city"))
       .agg(
           avg("temperature").alias("avg_temp"),
           avg("windspeed").alias("avg_wind")
       )
       .select(
           col("window.start").alias("window_start"),
           col("window.end").alias("window_end"),
           col("city"),
           round(col("avg_temp"), 2).alias("avg_temp"),
           round(col("avg_wind"), 2).alias("avg_wind")
       ))


query = (agg.writeStream
         .outputMode("update")
         .format("console")
         .option("truncate", "false")
         .option("checkpointLocation", "/tmp/checkpoints/openmeteo_console")
         .trigger(processingTime="10 seconds")
         .start())

query.awaitTermination()

