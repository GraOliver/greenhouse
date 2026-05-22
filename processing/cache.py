"""Module de cache persistant JSON pour les données calculées.

Sauvegarde les données calculées (moyennes, comparaisons) dans un fichier JSON
pour survire aux actualisations de page, puis les migre vers la BDD toutes les heures.
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path


# Chemin du fichier cache JSON
CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cache'))
CACHE_FILE = os.path.join(CACHE_DIR, 'sensor_data_cache.json')


def ensure_cache_dir():
    """Crée le répertoire cache s'il n'existe pas."""
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)


def save_sensor_data_to_cache(gh_id: str, calculation_result: dict):
    """Sauvegarde les données calculées dans le cache JSON.
    
    Args:
        gh_id: identifiant de la serre
        calculation_result: résultat de process_raw_sensor_message()
    """
    ensure_cache_dir()
    
    # Charger les données existantes
    cache_data = load_cache()
    
    # Ajouter/mettre à jour les données pour cette serre
    if gh_id not in cache_data:
        cache_data[gh_id] = {
            'computed': {},
            'comparison': {},
            'entries': []
        }
    
    # Enregistrer une nouvelle entrée avec timestamp
    entry = {
        'timestamp': time.time(),
        'datetime': datetime.now().isoformat(),
        'computed': calculation_result.get('computed', {}),
        'comparison': calculation_result.get('comparison', {})
    }
    
    cache_data[gh_id]['entries'].append(entry)
    
    # Garder seulement les 1000 dernières entrées par serre
    if len(cache_data[gh_id]['entries']) > 1000:
        cache_data[gh_id]['entries'] = cache_data[gh_id]['entries'][-1000:]
    
    # Mettre à jour les données actuelles
    cache_data[gh_id]['computed'] = calculation_result.get('computed', {})
    cache_data[gh_id]['comparison'] = calculation_result.get('comparison', {})
    
    # Écrire dans le fichier
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du cache : {e}")


def load_cache() -> dict:
    """Charge les données depuis le cache JSON.
    
    Returns: dictionnaire avec les données en cache, ou {} si le fichier n'existe pas
    """
    ensure_cache_dir()
    
    if not os.path.exists(CACHE_FILE):
        return {}
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lors de la lecture du cache : {e}")
        return {}


def get_cache_data(gh_id: str) -> dict:
    """Récupère les données en cache pour une serre.
    
    Returns: dictionnaire contenant 'computed', 'comparison', et 'entries'
    """
    cache_data = load_cache()
    if gh_id in cache_data:
        return cache_data[gh_id]
    return {
        'computed': {},
        'comparison': {},
        'entries': []
    }


def get_cache_entries(gh_id: str, limit: int = 100) -> list:
    """Récupère les dernières entrées en cache pour une serre.
    
    Args:
        gh_id: identifiant de la serre
        limit: nombre maximum d'entrées à retourner
    
    Returns: liste des dernières entrées
    """
    cache_data = get_cache_data(gh_id)
    entries = cache_data.get('entries', [])
    return entries[-limit:] if entries else []


def clear_cache_for_serre(gh_id: str):
    """Vide le cache pour une serre donnée (généralement après migration vers BDD)."""
    ensure_cache_dir()
    cache_data = load_cache()
    
    if gh_id in cache_data:
        cache_data[gh_id] = {
            'computed': {},
            'comparison': {},
            'entries': []
        }
    
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la suppression du cache : {e}")


def clear_all_cache():
    """Vide complètement le cache."""
    ensure_cache_dir()
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors du vidage du cache : {e}")
