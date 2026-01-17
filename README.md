# Pipeline Big Data - Traitement Temps Réel de Données Météorologiques

## 📋 Description du Projet

Ce projet implémente un pipeline de données distribué pour le traitement temps réel de données météorologiques. Le système collecte les données depuis l'API Open-Meteo, les traite via Apache Spark Streaming et les visualise dans Grafana.

### Objectifs
- Démonstration d'un cluster Big Data distribué
- Traitement temps réel avec Kafka + Spark Streaming  
- Visualisation de métriques avec InfluxDB + Grafana
- Gestion de la charge et optimisation des ressources

### Défis Rencontrés et Solutions
- **Problème initial** : Surcharge du Master (crashs fréquents)
- **Solution appliquée** : 
  - Réduction de 5 à 3 villes 
  - Intervalle de collecte de 10s → 60s
  - Producer déplacé sur Worker1

## 🏗️ Architecture Distribuée

### Configuration du Cluster (4 VMs Azure)
| Node | IP | CPU/RAM | Services |
|------|----|---------| ---------|
| Master | 10.0.0.110 | 4 vCPU / 8GB | NameNode, ResourceManager, InfluxDB, Grafana |
| Worker1 | 10.0.0.111 | 2 vCPU / 4GB | DataNode, Kafka Broker 1, ZooKeeper, Producer |
| Worker2 | 10.0.0.102 | 2 vCPU / 4GB | DataNode, Kafka Broker 2 |
| Worker3 | 10.0.0.103 | 2 vCPU / 4GB | DataNode, Kafka Broker 3 |

### Flux de Données
```
API Open-Meteo → Producer Python → Kafka (3 brokers) → Spark Streaming → InfluxDB → Grafana
```

### Source de Données : API Open-Meteo
- **URL** : https://api.open-meteo.com/v1/forecast
- **Villes** : Paris, Nice, Strasbourg
- **Métriques** : Température, vitesse du vent, humidité, pression
- **Fréquence** : 60 secondes (optimisé pour éviter surcharge)

## 🚀 Guide de Démarrage Complet

### Prérequis
- 4 VMs Ubuntu configurées en réseau
- Java 11+ installé sur tous les nodes
- Python 3.8+ avec pip et venv

### 1. Services Hadoop (sur Master)
```bash
# Démarrer HDFS
start-dfs.sh

# Vérifier HDFS
hdfs dfsadmin -report

# Démarrer YARN
start-yarn.sh

# Vérifier YARN
yarn node -list
```

### 2. Système Kafka Distribué

#### A. ZooKeeper (sur Worker1 UNIQUEMENT)
```bash
ssh adm-mcsc@10.0.0.111
cd /opt/kafka
./bin/zookeeper-server-start.sh -daemon config/zookeeper.properties

# Vérifier ZooKeeper
jps | grep QuorumPeerMain
```

#### B. Brokers Kafka (sur TOUS les Workers)
```bash
# Sur Worker1
./bin/kafka-server-start.sh -daemon config/server.properties

# Sur Worker2
ssh adm-mcsc@10.0.0.102
cd /opt/kafka
./bin/kafka-server-start.sh -daemon config/server.properties

# Sur Worker3  
ssh adm-mcsc@10.0.0.103
cd /opt/kafka
./bin/kafka-server-start.sh -daemon config/server.properties
```

#### C. Créer le Topic
```bash
# Depuis n'importe quel node
/opt/kafka/bin/kafka-topics.sh --create \
  --topic open-meteo-weather \
  --bootstrap-server 10.0.0.111:9092,10.0.0.102:9092,10.0.0.103:9092 \
  --partitions 3 \
  --replication-factor 3

# Vérifier la création
/opt/kafka/bin/kafka-topics.sh --describe \
  --topic open-meteo-weather \
  --bootstrap-server 10.0.0.111:9092,10.0.0.102:9092,10.0.0.103:9092
```

### 3. Base de Données InfluxDB (sur Master)
```bash
cd ~/influxdb2_linux_amd64
./influxd &

# Dans un autre terminal, configurer
influx setup \
  --username admin \
  --password adminpassword \
  --org admin \
  --bucket open_meteo_metrics \
  --force
```

### 4. Grafana (sur Master)
```bash
# Nouveau terminal
~/grafana-10.2.0/bin/grafana-server \
  --homepath ~/grafana-10.2.0 \
  --config ~/grafana-10.2.0/conf/defaults.ini &
```

## 🔄 Exécution du Pipeline

### Étape 1 : Lancer le Producer de Données (sur Worker1)
```bash
# Se connecter au Worker1
ssh adm-mcsc@10.0.0.111
cd ~/streaming_project/spark_jobs

# Créer et activer l'environnement virtuel Python
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install kafka-python requests

# Lancer le producer en arrière-plan
python3 open_meteo_producer.py

# Pour lancer en arrière-plan (optionnel)
nohup python3 open_meteo_producer.py > producer.log 2>&1 &

# Vérifier les logs
tail -f producer.log
```

### Étape 2 : Lancer Spark Streaming (sur Master)
```bash
# Sur Master
cd ~/streaming_project/spark_jobs

# Configurer les variables d'environnement
export INFLUX_ORG="admin"
export INFLUX_BUCKET="open_meteo_metrics"
export INFLUX_TOKEN="votre-token-ici"

# Lancer le job Spark
spark-submit \
  --master yarn \
  --deploy-mode client \
  --executor-memory 1G \
  --executor-cores 1 \
  --num-executors 2 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
  spark_openmeteo_to_influx.py
```

### Étape 3 : Accéder aux Interfaces
```bash
# Depuis votre machine locale - Tunnels SSH
ssh -L 8088:localhost:8088 -L 8086:localhost:8086 -L 3000:localhost:3000 adm-mcsc@master

# Puis ouvrir :
# - YARN UI : http://localhost:8088
# - InfluxDB : http://localhost:8086  
# - Grafana : http://localhost:3000
```

## 📊 Configuration Grafana

1. **Ajouter InfluxDB comme source** :
   - URL : `http://localhost:8086`
   - Organisation : `admin`
   - Token : votre token InfluxDB
   - Bucket : `open_meteo_metrics`

2. **Requête exemple pour dashboard** :
```flux
from(bucket: "open_meteo_metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "weather")
  |> filter(fn: (r) => r["_field"] == "temperature")
  |> aggregateWindow(every: 1m, fn: mean)
```

## 🛠️ Technologies et Versions

- **Hadoop** : 3.3.6 (HDFS + YARN)
- **Apache Spark** : 3.5.1 (Structured Streaming)
- **Apache Kafka** : 3.7.2 (3 brokers + ZooKeeper)
- **InfluxDB** : 2.7.1 (Time Series Database)
- **Grafana** : 10.2.0 (Visualisation)
- **Python** : 3.8+ (Producer + librairies : kafka-python, requests)

## 🔍 Monitoring et Dépannage

### Vérifier les Services
```bash
# Hadoop
jps  # Voir les processus Java
hdfs dfsadmin -report | head -10

# Kafka  
/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server 10.0.0.111:9092

# Vérifier les messages Kafka
/opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server 10.0.0.111:9092 \
  --topic open-meteo-weather \
  --from-beginning \
  --max-messages 5
```

### Logs Importants
- Producer : `~/streaming_project/spark_jobs/producer.log`
- Spark : Interface YARN UI
- Kafka : `/opt/kafka/logs/`
- InfluxDB : Logs dans le terminal
- Grafana : Logs dans le terminal

## 🎥 Démonstration Vidéo
[Lien YouTube de la démonstration complète](à-ajouter)

## 📄 License
MIT License - Voir fichier LICENSE
