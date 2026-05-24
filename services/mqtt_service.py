#=====================================================
# Nous allons créer un service MQTT pour gérer les communications entre les capteurs et actionneurs de la serre et notre application Flask.
# Ce service se connectera à un broker MQTT, s'abonnera aux topics des capteurs, et publiera des commandes aux actionneurs.
#=====================================================
import paho.mqtt.client as mqtt
import json
import queue
import time
from processing.processor import process_raw_sensor_message, LATEST_COMPARTMENT_DATA
from processing.cache import save_sensor_data_to_cache
from models.database import save_history_event
from models.greenhouse import get_greenhouse
from models.culture import get_culture

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
    q = queue.Queue(maxsize=100)   # Limite de 5 messages en attente pour éviter les débordements
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
        print(f"Reçu message MQTT sur {msg.topic} : {data}")
    except Exception:
        data = {'raw': msg.payload.decode()}

    # Traiter les messages MQTT
    parts = msg.topic.split('/')
    if len(parts) >= 4:
        # Cas: device status, ex: nsele/device/<idserre>/status
        if parts[1] == 'device' and parts[3].lower() == 'status':
            gh_id = parts[2]
            status_str = payload.strip().upper() if isinstance(payload, str) else str(payload)
            status_str = status_str.strip().upper()
            print(f"Reçu statut MQTT pour {gh_id} : {status_str}")
            # Si l'ESP32 annonce ONLINE, nous envoyons les seuils configurés
            if status_str == 'ONLINE':
                try:
                    gh = get_greenhouse(gh_id)
                    if gh and gh.get('culture_id'):
                        cult = get_culture(gh.get('culture_id'))
                    else:
                        cult = None

                    thresholds = {
                        'hs_min': None,
                        'hs_max': None,
                        'ha_min': None,
                        'ha_max': None,
                        'ts_min': None,
                        'ts_max': None,
                        'ta_min': None,
                        'ta_max': None,
                    }

                    if cult:
                        thresholds['hs_min'] = cult.get('humidite_sol_min')
                        thresholds['hs_max'] = cult.get('humidite_sol_max')
                        thresholds['ha_min'] = cult.get('humidite_air_min')
                        thresholds['ha_max'] = cult.get('humidite_air_max')
                        thresholds['ts_min'] = cult.get('temperature_sol_min')
                        thresholds['ts_max'] = cult.get('temperature_sol_max')
                        thresholds['ta_min'] = cult.get('temperature_air_min')
                        thresholds['ta_max'] = cult.get('temperature_air_max')

                    topic_out = f"nsele/device/{gh_id}/data"
                    payload_out = json.dumps(thresholds)
                    client.publish(topic_out, payload_out)
                    print(f"Envoyé seuils à {topic_out} : {payload_out}")
                except Exception as e:
                    print(f"Erreur en traitant device status pour {gh_id}: {e}")
            return

        # Cas: messages de capteurs habituels ex: nsele/raw_sensor/<gh_id>/<comp_id> ou nsele/row_sensor/<gh_id>/<comp_id>
        # Vérifier que le topic est bien un topic capteur
        if parts[1] not in ('raw_sensor', 'row_sensor'):
            print(f"Format de topic inattendu : {msg.topic}. Attendu 'nsele/raw_sensor/<gh_id>/<comp_id>' ou 'nsele/row_sensor/<gh_id>/<comp_id>'.")
            return
        
        gh_id = parts[2]  # ID de la serre
        comp_id = parts[3]  # ID du compartiment

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
            # Calculer et diffuser immédiatement les moyennes globales pour cette serre
            try:
                comps = result.get('computed', {}).get(gh_id, {})
                totalTA = totalTS = totalHA = totalHS = 0.0
                for comp in comps.values():
                    if comp.get('ta') is not None:
                        totalTA += float(comp.get('ta'))
                    if comp.get('ts') is not None:
                        totalTS += float(comp.get('ts'))
                    if comp.get('ha') is not None:
                        totalHA += float(comp.get('ha'))
                    if comp.get('hs') is not None:
                        totalHS += float(comp.get('hs'))
                
                # Diviser par le NOMBRE TOTAL de compartiments enregistrés en cache (option 1)
                total_comp_count = len(LATEST_COMPARTMENT_DATA.get(gh_id, {}))
                if total_comp_count == 0:
                    total_comp_count = len(comps) if comps else 1
                
                if total_comp_count > 0:
                    averages_payload = {
                        'TA': round(totalTA / total_comp_count, 1),
                        'TS': round(totalTS / total_comp_count, 1),
                        'HA': round(totalHA / total_comp_count, 1),
                        'HS': round(totalHS / total_comp_count, 1),
                    }
                else:
                    averages_payload = {'TA': None, 'TS': None, 'HA': None, 'HS': None}

                averages_topic = f"nsele/averages/{gh_id}/averages"
                broadcast_sensor_data(averages_topic, averages_payload)
            except Exception:
                pass

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
        print(f"Format de topic inattendu : {msg.topic}. Attendu 'nsele/raw_sensor/<gh_id>/<comp_id>' ou 'nsele/row_sensor/<gh_id>/<comp_id>'.")
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
