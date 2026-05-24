#=====================================================
# Nous allons créer un service MQTT pour gérer les communications entre les capteurs et actionneurs de la serre et notre application Flask.
# Ce service se connectera à un broker MQTT, s'abonnera aux topics des capteurs, et publiera des commandes aux actionneurs.
#=====================================================
import paho.mqtt.client as mqtt
import json
import queue
import time
from processing.processor import process_raw_sensor_message
from processing.cache import save_sensor_data_to_cache
from models.database import save_history_event

# Configuration du broker MQTT
MQTT_BROKER = '192.168.1.173' # Le IPV de la machine ici nous sommess en locale
MQTT_PORT = 1883
client = mqtt.Client() # creation client

# Liste de files d'attente (Queues) pour les clients SSE connectés (HTML pages)
sse_listeners = []

# Dictionnaire global pour stocker les dernières données calculées par greenhouse
# Format : { 'S1': {'computed': {...}, 'comparison': {...}, 'timestamp': ...}, ... }
sensor_data_store = {}

def register_listener():
    """Enregistre un nouveau client SSE et retourne sa file d'attente dédiée."""
    q = queue.Queue(maxsize=100)   # Limite de 100 messages en attente pour éviter les débordements
    sse_listeners.append(q)
    return q

# Fonction pour supprimer un client SSE de la liste des listeners
def unregister_listener(q):
    """Supprime un client SSE de la liste des listeners."""
    if q in sse_listeners:
        try:
            sse_listeners.remove(q)
        except ValueError:
            pass

# Fonction pour diffuser les données des capteurs à tous les clients SSE connectés
def broadcast_sensor_data(topic, payload):
    """Diffuse les données des capteurs à tous les clients SSE connectés."""
    message = {
        'topic': topic,
        'payload': payload
    }
    for q in list(sse_listeners):
        try:
            q.put_nowait(message)
        except queue.Full:
            # Si la file d'attente est pleine, on peut choisir de supprimer le plus ancien message
            try:
                q.get_nowait()  # Supprimer le plus ancien message
                q.put_nowait(message)  # Ajouter le nouveau message
            except Exception:
                pass
            
# Fonction pour publier une commande de contrôle manuel à un actionneur
def publish_actuator_command(gh_id, actuator_type, state):
    """
    Publie une commande de contrôle pour un actionneur (pompe, cooling, etc.)
    sur le broker MQTT sous le sujet 'nsele/actuator/<gh_id>/<actuator_type>'.
    """
    try:
        topic = f"nsele/actuator/{gh_id}/{actuator_type}"
        payload = json.dumps({'state': state.upper()})
        client.publish(topic, payload)
        print(f"Commande MQTT publiée sur {topic} : {payload}")
        return True
    except Exception as e:
        print(f"Erreur lors de la publication de la commande MQTT : {e}")
        return False

# Fonction de rappel pour la connexion MQTT
def on_connect(client, userdata, flags, rc):
    """Callback appelé lors de la connexion au broker MQTT."""
    print('MQTT connected with result code', rc)
    # S'abonner à tous les sujets sous nsele/ (raw_sensors, sensors, actuators)
    client.subscribe('nsele/#')


# Fonction pour récupérer les dernières données calculées pour une serre
def get_sensor_data(gh_id):
    """Retourne les données calculées stockées pour une serre donnée."""
    return sensor_data_store.get(gh_id, None)

# Fonction de rappel pour la réception de messages MQTT
def on_message(client, userdata, msg):
    """Callback appelé lors de la réception d'un message MQTT."""
    try:
        payload = msg.payload.decode() # pour lire les information
        data = json.loads(payload)
        
    except Exception:
        data = {'raw': msg.payload.decode()}

    # Traiter les données brutes des capteurs
    # if msg.topic.startswith('nsele/raw_sensor/'):
    parts = msg.topic.split('/')
    if len(parts) >= 4:
        gh_id = parts[2]  # ID de la serre
        comp_id = parts[3]  # ID du compartiment
            
            # Appeler le processor pour calculer moyennes et comparaison
        try:
            result = process_raw_sensor_message(gh_id, comp_id, data['raw'] if 'raw' in data else data)
            # Stocker le résultat pour accès futur (via API)
            if gh_id not in sensor_data_store:
                sensor_data_store[gh_id] = {}
            sensor_data_store[gh_id] = {
                'computed': result.get('computed', {}),
                'comparison': result.get('comparison', {}),
                'timestamp': time.time()
                }
            # Sauvegarder les données calculées dans le cache JSON pour persistence
            save_sensor_data_to_cache(gh_id, result)
                
            # Enregistrer les données capteur dans l'historique immédiatement
            raw_data = data['raw'] if 'raw' in data else data
            if isinstance(raw_data, dict):
                details = f"Mesure capteur: TA={raw_data.get('ta')}°C, TS={raw_data.get('ts')}°C, HA={raw_data.get('ha')}%, HS={raw_data.get('hs')}%"
            else:
                details = f"Mesure capteur: {raw_data}"
            save_history_event(gh_id, comp_id, 'capteur', details)

        except Exception as e:
            print(f"Erreur lors du traitement des données : {e}")
            
    else:
        print(f"Format de topic inattendu : {msg.topic}. Attendu 'nsele/raw_sensor/<gh_id>/<comp_id>'.")
        return

    
    # Diffuser les données à tous les clients SSE connectés
    broadcast_sensor_data(msg.topic, data)
    
def mqtt_start():
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Ecouter MQTT en permance 
        print(f"Service MQTT démarré sur {MQTT_BROKER}:{MQTT_PORT}")
        
    except ConnectionRefusedError:
        print(f"AVERTISSEMENT : Impossible de se connecter au broker MQTT sur {MQTT_BROKER}:{MQTT_PORT}. Assurez-vous que Mosquitto est lance.")
    except Exception as e:
        print(f"Erreur MQTT : {e}")
