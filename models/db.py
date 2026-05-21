import json
import os

# Chemin absolu vers le fichier de persistance JSON
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')

# Données d'initialisation par défaut de l'application
DEFAULT_DATA = {
    "greenhouses": [
        {"id": "S1", "name": "Serre 1", "culture": "tomates", "status": "OK"},
        {"id": "S2", "name": "Serre 2", "culture": "laitue", "status": "OK"},
        {"id": "S3", "name": "Serre 3", "culture": "poivrons", "status": "OK"},
        {"id": "S4", "name": "Serre 4", "culture": "aubergines", "status": "OK"}
    ],
    "cultures": [
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
        },
        {
            "id": "laitue",
            "name": "Laitue",
            "min_temp_air": 15.0,
            "max_temp_air": 22.0,
            "min_temp_sol": 12.0,
            "max_temp_sol": 20.0,
            "min_hum_air": 60.0,
            "max_hum_air": 85.0,
            "min_hum_sol": 40.0,
            "max_hum_sol": 80.0
        },
        {
            "id": "poivrons",
            "name": "Poivrons",
            "min_temp_air": 20.0,
            "max_temp_air": 32.0,
            "min_temp_sol": 18.0,
            "max_temp_sol": 28.0,
            "min_hum_air": 50.0,
            "max_hum_air": 75.0,
            "min_hum_sol": 35.0,
            "max_hum_sol": 75.0
        },
        {
            "id": "aubergines",
            "name": "Aubergines",
            "min_temp_air": 22.0,
            "max_temp_air": 35.0,
            "min_temp_sol": 18.0,
            "max_temp_sol": 30.0,
            "min_hum_air": 55.0,
            "max_hum_air": 80.0,
            "min_hum_sol": 35.0,
            "max_hum_sol": 75.0
        }
    ]
}

def load_data():
    """
    Charge les données depuis le fichier JSON.
    Si le fichier n'existe pas, il le crée avec les données par défaut.
    """
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return DEFAULT_DATA

def save_data(data):
    """
    Sauvegarde l'état des données dans le fichier JSON.
    """
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print("Erreur de sauvegarde JSON:", e)
