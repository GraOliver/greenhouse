import os
import sqlite3
from models.db import load_data

# Chemin du fichier SQLite (serre.db à la racine du projet)
DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'serre.db'))


def get_db_path() -> str:
    """Retourne le chemin vers le fichier de base de données SQLite."""
    return DB_FILE


def get_db_connection():
    """Ouvre et retourne une connexion SQLite avec Row factory.

    N'utilise PAS de création de schéma au moment de l'import ; appeler
    `initialize_database()` depuis le code d'initialisation de l'app.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    """Crée les tables nécessaires si elles n'existent pas déjà."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS cultures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL UNIQUE,
            description TEXT,
            temperature_sol_min REAL,
            temperature_sol_max REAL,
            temperature_air_min REAL,
            temperature_air_max REAL,
            humidite_sol_min REAL,
            humidite_sol_max REAL,
            humidite_air_min REAL,
            humidite_air_max REAL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS serres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL UNIQUE,
            description TEXT,
            culture_id TEXT,
            compartiment INTEGER
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS serre_compartments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serre_nom TEXT NOT NULL,
            compartment TEXT NOT NULL,
            UNIQUE(serre_nom, compartment)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serre_id INTEGER,
            temperature_air REAL,
            humidite_air REAL,
            temperature_sol REAL,
            humidite_sol REAL,
            quantite_eau REAL,
            date_mesure DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS actionneurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serre_id INTEGER,
            nom TEXT NOT NULL,
            type TEXT,
            etat TEXT DEFAULT 'OFF'
        )
    ''')

    # Table pour stocker le journal unifié de l'historique (capteurs et actionneurs)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS history_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_heure DATETIME DEFAULT CURRENT_TIMESTAMP,
            serre_id TEXT NOT NULL,
            compartiment TEXT,
            type_event TEXT NOT NULL,
            details TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()


def seed_database_from_json():
    """Insère dans SQLite les données initiales présentes dans `data.json` si absentes."""
    data = load_data()
    conn = get_db_connection()
    cur = conn.cursor()

    for culture in data.get('cultures', []):
        cur.execute(
            "INSERT OR IGNORE INTO cultures (nom, description, temperature_sol_min, temperature_sol_max, temperature_air_min, temperature_air_max, humidite_sol_min, humidite_sol_max, humidite_air_min, humidite_air_max) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                culture['id'],
                culture.get('name', culture['id']),
                float(culture.get('min_temp_sol', 0.0)),
                float(culture.get('max_temp_sol', 0.0)),
                float(culture.get('min_temp_air', 0.0)),
                float(culture.get('max_temp_air', 0.0)),
                float(culture.get('min_hum_sol', 0.0)),
                float(culture.get('max_hum_sol', 0.0)),
                float(culture.get('min_hum_air', 0.0)),
                float(culture.get('max_hum_air', 0.0))
            )
        )

    for greenhouse in data.get('greenhouses', []):
        compartments = greenhouse.get('compartments', ["C1", "C2", "C3", "C4"]) if isinstance(greenhouse, dict) else ["C1", "C2", "C3", "C4"]
        cur.execute(
            "INSERT OR IGNORE INTO serres (nom, description, culture_id, compartiment) VALUES (?, ?, ?, ?)",
            (
                greenhouse.get('id', greenhouse.get('name')),
                greenhouse.get('name', greenhouse.get('id')),
                greenhouse.get('culture'),
                len(compartments)
            )
        )
        for comp in compartments:
            cur.execute(
                "INSERT OR IGNORE INTO serre_compartments (serre_nom, compartment) VALUES (?, ?)",
                (greenhouse.get('id', greenhouse.get('name')), comp)
            )

    conn.commit()
    conn.close()


def initialize_database():
    """Crée les tables si nécessaires et insère les données initiales si la base est vide.

    Appeler cette fonction au démarrage de l'application (ou avant toute opération
    qui suppose l'existence des tables).
    """
    create_tables()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM serres")
    serre_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cultures")
    culture_count = cur.fetchone()[0]
    conn.close()

    if serre_count == 0 or culture_count == 0:
        seed_database_from_json()


# Fonction d'aide pour sauvegarder un événement dans l'historique (capteurs ou actionneurs)
def save_history_event(serre_id, compartiment, type_event, details):
    """
    Enregistre un événement dans la table 'history_logs' de SQLite.
    Commenté en français pour expliquer chaque étape.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insertion des données de l'événement dans la table history_logs
        cursor.execute(
            """
            INSERT INTO history_logs (serre_id, compartiment, type_event, details) 
            VALUES (?, ?, ?, ?)
            """,
            (
                serre_id.upper(), 
                compartiment.upper() if compartiment else '--', 
                type_event, 
                details
            )
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de l'historique dans SQLite : {e}")
        return False