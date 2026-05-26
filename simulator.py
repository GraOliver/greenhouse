import paho.mqtt.client as mqtt
import json
import time
import random

# Configuration
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883

# Définition des 4 serres et leurs compartiments
GREENHOUSES = {
    'S1': ['C1', 'C2', 'C3', 'C4'],
    'S2': ['C1', 'C2', 'C3', 'C4'],
    'S3': ['C1', 'C2', 'C3', 'C4'],
    'S4': ['C1', 'C2', 'C3', 'C4'],
}

# Profils de température légèrement différents par serre pour un rendu réaliste
GREENHOUSE_PROFILES = {
    'S1': {'ta_offset': 0.0,  'ts_offset': 0.0,  'ha_offset': 0.0,  'hs_offset': 0.0},
    'S2': {'ta_offset': 1.5,  'ts_offset': 0.8,  'ha_offset': -5.0, 'hs_offset': 3.0},
    'S3': {'ta_offset': -1.0, 'ts_offset': 1.2,  'ha_offset': 8.0,  'hs_offset': -4.0},
    'S4': {'ta_offset': 2.0,  'ts_offset': -0.5, 'ha_offset': 3.0,  'hs_offset': 6.0},
}


def generate_sensor_data(gh_id, comp_id, trigger_alert=False):
    """
    Génère des données de capteur aléatoires pour une serre et un compartiment donnés.
    Applique un profil propre à chaque serre pour des valeurs réalistes et variées.
    Si trigger_alert est True, génère des valeurs extrêmes pour forcer les alertes.
    """
    profile = GREENHOUSE_PROFILES.get(gh_id, GREENHOUSE_PROFILES['S1'])

    if trigger_alert:
        # Valeurs extrêmes pour déclencher les alertes
        return {
            'ta': round(random.uniform(35.0, 42.0) + profile['ta_offset'], 1),  # Trop chaud
            'ts': round(random.uniform(30.0, 35.0) + profile['ts_offset'], 1),  # Sol trop chaud
            'ha': round(random.uniform(40.0, 60.0) + profile['ha_offset'], 1),  # Normal
            'hs': round(random.uniform(10.0, 20.0) + profile['hs_offset'], 1),  # Sol trop sec
        }
    else:
        # Valeurs normales avec légère variation par compartiment
        comp_offset = {'C1': 0.0, 'C2': 0.3, 'C3': -0.3, 'C4': 0.5}.get(comp_id, 0.0)
        return {
            'ta': round(random.uniform(20.0, 25.0) + profile['ta_offset'] + comp_offset, 1),
            'ts': round(random.uniform(18.0, 22.0) + profile['ts_offset'] + comp_offset, 1),
            'ha': round(random.uniform(50.0, 70.0) + profile['ha_offset'], 1),
            'hs': round(random.uniform(40.0, 60.0) + profile['hs_offset'], 1),
        }


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connecté au broker MQTT avec succès !")
    else:
        print(f"❌ Échec de la connexion. Code : {rc}")


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

    print("\n--- DÉBUT DE LA SIMULATION (4 SERRES) ---")
    print(f"Serres simulées : {', '.join(GREENHOUSES.keys())}")
    print("Envoi de données alternant entre normales et critiques...\n")

    try:
        while True:
            cycle_count += 1
            # Alterner : 2 cycles normaux, puis 1 critique
            trigger_alert = (cycle_count % 3 == 0)

            label = "⚠️  DONNÉES CRITIQUES" if trigger_alert else "✅ Données normales"
            print(f"{'='*55}")
            print(f"[Cycle {cycle_count}] {label}")
            print(f"{'='*55}")

            for gh_id, compartments in GREENHOUSES.items():
                print(f"\n  🏠 Serre {gh_id} :")
                for comp_id in compartments:
                    topic = f"nsele/raw_sensor/{gh_id}/{comp_id}"
                    data = generate_sensor_data(gh_id, comp_id, trigger_alert)
                    payload = json.dumps(data)
                    client.publish(topic, payload)
                    print(f"    📡 {topic} → TA={data['ta']}°C | TS={data['ts']}°C | HA={data['ha']}% | HS={data['hs']}%")
                    time.sleep(0.5)  # Courte pause entre les compartiments

            print(f"\n⏳ Attente de 10 secondes avant le prochain cycle...")
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n\nSimulation arrêtée par l'utilisateur.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    run_simulation()
