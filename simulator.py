import paho.mqtt.client as mqtt
import json
import time
import random

# Configuration
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
GREENHOUSE_ID = 'S1'
COMPARTMENTS = ['C1', 'C2', 'C3', 'C4']

def generate_sensor_data(comp_id, trigger_alert=False):
    """
    Génère des données de capteur aléatoires.
    Si trigger_alert est True, génère des valeurs extrêmes pour forcer les alertes.
    """
    if trigger_alert:
        # Valeurs extrêmes pour déclencher les alertes
        # ta > max, ts > max, hs < min
        return {
            'ta': round(random.uniform(35.0, 42.0), 1), # Trop chaud
            'ts': round(random.uniform(30.0, 35.0), 1), # Sol trop chaud
            'ha': round(random.uniform(40.0, 60.0), 1), # Normal
            'hs': round(random.uniform(10.0, 20.0), 1)  # Sol trop sec
        }
    else:
        # Valeurs normales
        return {
            'ta': round(random.uniform(20.0, 25.0), 1),
            'ts': round(random.uniform(18.0, 22.0), 1),
            'ha': round(random.uniform(50.0, 70.0), 1),
            'hs': round(random.uniform(40.0, 60.0), 1)
        }

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connecté au broker MQTT avec succès !")
    else:
        print(f"Échec de la connexion. Code : {rc}")

def run_simulation():
    client = mqtt.Client()
    client.on_connect = on_connect
    
    print(f"Connexion au broker {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"Erreur de connexion : {e}. Vérifiez que Mosquitto est bien lancé.")
        return

    client.loop_start()

    cycle_count = 0
    
    print("\n--- DÉBUT DE LA SIMULATION ---")
    print("Envoi de données alternant entre normales et critiques...")
    
    try:
        while True:
            cycle_count += 1
            # Alterner : 2 cycles normaux, puis 1 critique
            trigger_alert = (cycle_count % 3 == 0)
            
            print(f"\n[Cycle {cycle_count}] " + ("⚠️ DONNÉES CRITIQUES" if trigger_alert else "✅ Données normales"))
            
            for comp_id in COMPARTMENTS:
                topic = f"nsele/raw_sensor/{GREENHOUSE_ID}/{comp_id}"
                data = generate_sensor_data(comp_id, trigger_alert)
                
                payload = json.dumps(data)
                client.publish(topic, payload)
                print(f"Publié sur {topic} : {payload}")
                
                time.sleep(1) # Petite pause entre les compartiments
                
            print("Attente de 10 secondes avant le prochain cycle...")
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nSimulation arrêtée par l'utilisateur.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_simulation()
