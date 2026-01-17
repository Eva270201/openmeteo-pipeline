import json
import time
from datetime import datetime, timezone

import requests
from kafka import KafkaProducer

TOPIC = "open-meteo-weather"
BOOTSTRAP_SERVERS = ["10.0.0.111:9092", "10.0.0.102:9092", "10.0.0.103:9092"]


CITIES = {
    "Paris":       {"lat": 48.8566, "lon": 2.3522},
    "Lyon":        {"lat": 45.7640, "lon": 4.8357},
    "Bordeaux":    {"lat": 44.8378, "lon": -0.5792},
    "Nice":        {"lat": 43.7102, "lon": 7.2620},
    "Strasbourg":  {"lat": 48.5734, "lon": 7.7521},
}

def fetch_weather(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "timezone": "UTC"
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    
    return data.get("current_weather", {})

def main():
    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=5,
        linger_ms=10,
    )

    print("✅ Kafka producer connecté")
    print("📡 Envoi des données météo (5 villes) vers Kafka... Ctrl+C pour arrêter")

    while True:
        for city, coords in CITIES.items():
            try:
                weather = fetch_weather(coords["lat"], coords["lon"])

                payload = {
                    "source": "open-meteo",
                    "city": city,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "weather": {
                        "time": weather.get("time"),
                        "temperature": weather.get("temperature"),
                        "windspeed": weather.get("windspeed"),
                        "winddirection": weather.get("winddirection"),
                        "weathercode": weather.get("weathercode"),
                        "is_day": weather.get("is_day"),
                    },
                }

                producer.send(TOPIC, value=payload)
                producer.flush()

                print(f"📨 Message envoyé ({city}) :", payload)

            except Exception as e:
                print(f"❌ Erreur pour {city}: {e}")

            
            time.sleep(2)

        
        time.sleep(5)

if __name__ == "__main__":
    main()

