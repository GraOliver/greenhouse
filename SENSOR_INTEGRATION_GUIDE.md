# Guide d'Intégration des Capteurs et Traitement des Données

## Vue d'ensemble du flux

Les données des capteurs circulent à travers le système suivant ce flux :

```
MQTT Broker (capteurs)
    ↓
mqtt_service.py (écoute et reçoit)
    ↓
processor.py (calcule moyennes, compare avec historique et seuils)
    ↓
mqtt_service.py (stocke en mémoire)
    ↓
views/pages.py API (/api/sensor-data/<gh_id>)
    ↓
static/js/dashboard.js (polling toutes les 5 secondes)
    ↓
dashboard.html (affichage temps réel)
```

## Format des messages MQTT

Les capteurs publient sur : `nsele/raw_sensor/<gh_id>/<comp_id>`

Exemple de payload JSON :
```json
{
  "ta": 24.5,
  "ts": 20.2,
  "ha": 68.0,
  "hs": 45.5
}
```

Où :
- `ta` = température air (°C)
- `ts` = température sol (°C)
- `ha` = humidité air (%)
- `hs` = humidité sol (%)

## Modules et fonctions principales

### 1. `processing/processor.py`

Traite les données brutes et produit des moyennes et décisions.

#### Fonctions clés :

**`normalize_ids(ids)`**
- Normalise les identifiants de serre/compartiment
- Accepte : chaîne `'S1,S2'` ou liste `['S1', 'S2']`
- Retourne : liste `['S1', 'S2']`

**`calc_average(values: List[float]) -> Optional[float]`**
- Calcule la moyenne d'une liste de nombres
- Retourne `None` si liste vide

**`fetch_historical_averages(serre_nom: str, limit: int = 20) -> Dict`**
- Récupère les dernières `limit` mesures de la base de données
- Calcule les moyennes : `ta`, `ts`, `ha`, `hs`
- Retourne : `{ "ta": 21.5, "ts": 19.2, "ha": 65.3, "hs": 42.1 }`

**`get_culture_thresholds_for_serre(serre_nom: str) -> Dict`**
- Récupère les seuils min/max de la culture liée à la serre
- Retourne : `{ "ta_min": 18, "ta_max": 30, "ts_min": 15, "ts_max": 25, ... }`

**`compare_with_db(averages: Dict) -> Dict`**
- Compare les moyennes courantes avec :
  - L'historique en base de données
  - Les seuils de la culture
- Produit une liste de `decisions` (alertes/actions recommandées)

**`process_raw_sensor_message(gh_id, comp_id, data) -> Dict`**
- Point d'entrée principal
- Accepte : `gh_id` (str ou liste), `comp_id` (str ou liste), `data` (dict)
- Retourne :
  ```python
  {
    'computed': { 'S1': { 'C1': {'ta': 24.5, 'ts': 20.2, 'ha': 68.0, 'hs': 45.5} } },
    'comparison': { 'S1': { 'C1': {
        'current': {...},
        'historical': {...},
        'thresholds': {...},
        'decisions': ['S1/C1: ta supérieur au seuil max ...']
    }}}
  }
  ```

### 2. `services/mqtt_service.py`

Écoute les messages MQTT et stocke les données calculées.

#### Variables/Fonctions clés :

**`sensor_data_store: Dict`**
- Dictionnaire global stockant les dernières données calculées
- Format : `{ 'S1': { 'computed': {...}, 'comparison': {...}, 'timestamp': 123456789 } }`

**`get_sensor_data(gh_id: str) -> Dict | None`**
- Récupère les données stockées pour une serre
- Utilisée par l'API

**`on_message(client, userdata, msg)`**
- Callback MQTT - traite chaque message reçu
- Appelle `process_raw_sensor_message()`
- Stocke le résultat dans `sensor_data_store`

### 3. `views/pages.py` - Routes API

**`GET /api/sensor-data/<gh_id>`**
- Récupère les données calculées stockées pour une serre
- Retourne :
  ```json
  {
    "computed": { "S1": { "C1": {...} } },
    "comparison": { "S1": { "C1": {...} } },
    "timestamp": 1234567890,
    "error": null
  }
  ```

### 4. `static/js/dashboard.js` - Logique frontend

**`fetchSensorCalculations(ghId)`**
- Polling toutes les 5 secondes (configurable via `sensorDataPollingInterval`)
- Appelle `/api/sensor-data/<ghId>`
- Met à jour les champs `avg-TA`, `avg-TS`, `avg-HA`, `avg-HS`
- Affiche les alertes/décisions si disponibles

## Exemple d'utilisation

### Simulation manuelle

```python
from processing.processor import process_raw_sensor_message
from models.database import initialize_database

# Initialiser la base
initialize_database()

# Message de capteur
msg = {'ta': 24.5, 'ts': 20.2, 'ha': 68.0, 'hs': 45.5}

# Traiter
result = process_raw_sensor_message('S1', 'C1', msg)

# Résultat
print(result['computed'])      # Moyennes calculées
print(result['comparison'])    # Comparaisons et décisions
```

### Via MQTT réel

1. Publier sur le broker MQTT local :
   ```bash
   mosquitto_pub -h localhost -t "nsele/raw_sensor/S1/C1" -m '{"ta":24.5,"ts":20.2,"ha":68.0,"hs":45.5}'
   ```

2. mqtt_service.py reçoit et traite automatiquement

3. Les données sont stockées dans `sensor_data_store`

4. Dashboard.js récupère via `/api/sensor-data/S1` et affiche

## Affichage dashboard

Le dashboard affiche :
- **Moyennes de la serre** : Temp. Air, Temp. Sol, Hum. Air, Hum. Sol (moyennes sur tous les compartiments)
- **Compartiments** : Carte pour chaque compartiment avec ses 4 valeurs + alertes si seuils dépassés
- **Graphique historique** : Évolution des moyennes au fil du temps
- **Alertes** : Messages en rouge si :
  - Valeur > seuil max de la culture
  - Valeur < seuil min de la culture
  - Valeur > moyenne historique

## Configuration

### Thresholds de cultures

Les seuils sont définis dans `models/data.json` ou directement en base de données (table `cultures`).

Exemple pour tomates :
```json
{
  "id": "tomates",
  "name": "Tomates",
  "min_temp_air": 18.0,
  "max_temp_air": 30.0,
  "min_temp_sol": 15.0,
  "max_temp_sol": 25.0,
  "min_hum_air": 50.0,
  "max_hum_air": 80.0,
  "min_hum_sol": 30.0,
  "max_hum_sol": 70.0
}
```

### Polling interval

Par défaut : 5 secondes. Pour changer, modifier dans `dashboard.js` :
```javascript
sensorDataPollingInterval = setInterval(() => fetchSensorCalculations(selectedId), 5000); // en ms
```

## Prochaines étapes possibles

1. **Actions automatisées** : Déclencher des relais/actionneurs basés sur les décisions
2. **Persistance** : Stocker toutes les mesures dans la table `mesures`
3. **WebSocket** : Remplacer le polling par SSE ou WebSocket pour push temps réel
4. **Machine Learning** : Prédire les variations basées sur l'historique
5. **Notifications** : Email/SMS en cas d'alerte critique

## Debug

Pour voir les logs dans la console Python :
```python
from processing.processor import process_raw_sensor_message
result = process_raw_sensor_message('S1', 'C1', {'ta':24.5,'ts':20.2,'ha':68.0,'hs':45.5})
# Logs affichés dans stdout
```

Pour inspecter les données stockées :
```python
from services.mqtt_service import sensor_data_store
print(sensor_data_store)
```

Pour checker les seuils d'une serre :
```python
from processing.processor import get_culture_thresholds_for_serre
print(get_culture_thresholds_for_serre('S1'))
```
