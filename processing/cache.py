"""Module de cache persistant JSON pour les données calculées.

Sauvegarde les données calculées (moyennes, comparaisons) dans un fichier JSON
pour survire aux actualisations de page, puis les migre vers la BDD toutes les heures.
"""

import os
import json
import time
import shutil
import threading
import tempfile
from json import JSONDecoder, JSONDecodeError
from datetime import datetime
from pathlib import Path


# Chemin du fichier cache JSON
CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cache'))
CACHE_FILE = os.path.join(CACHE_DIR, 'sensor_data_cache.json')
_cache_lock = threading.RLock()


def ensure_cache_dir():
    """Crée le répertoire cache s'il n'existe pas."""
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)


def _write_cache_file(cache_data: dict):
    """Écrit le cache vers le disque de façon atomique avec fichier temporaire unique."""
    ensure_cache_dir()

    if os.path.exists(CACHE_FILE):
        try:
            shutil.copy2(CACHE_FILE, CACHE_FILE + '.bak')
        except Exception:
            pass

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=CACHE_DIR,
            prefix='sensor_data_cache.',
            suffix='.tmp',
            delete=False
        ) as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
            tmp_file = f.name

        for attempt in range(5):
            try:
                os.replace(tmp_file, CACHE_FILE)
                return
            except (PermissionError, OSError) as e:
                if attempt < 4:
                    time.sleep(0.1)
                    continue
                raise
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def save_sensor_data_to_cache(gh_id: str, calculation_result: dict):
    """Sauvegarde les données calculées dans le cache JSON.
    
    Args:
        gh_id: identifiant de la serre
        calculation_result: résultat de process_raw_sensor_message()
    """
    with _cache_lock:
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

        try:
            _write_cache_file(cache_data)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du cache : {e}")


def load_cache() -> dict:
    """Charge les données depuis le cache JSON.
    
    Returns: dictionnaire avec les données en cache, ou {} si le fichier n'existe pas
    """
    with _cache_lock:
        ensure_cache_dir()

        if not os.path.exists(CACHE_FILE):
            return {}

        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except JSONDecodeError as e:
            print(f"Erreur lors de la lecture du cache : {e}")
        # Tentatives de récupération : NDJSON -> objets concaténés -> restauration .bak
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception:
            return {}

        # 1) NDJSON (une JSON par ligne)
        nd_objects = []
        try:
            for i, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                nd_objects.append(json.loads(line))
        except Exception:
            nd_objects = []

        if nd_objects:
            repaired_path = CACHE_FILE + '.repaired.ndjson.json'
            try:
                with open(repaired_path, 'w', encoding='utf-8') as rf:
                    json.dump(nd_objects, rf, indent=2, ensure_ascii=False)
                print(f"NDJSON détecté — version réparée écrite dans {repaired_path}")
            except Exception:
                pass
            return {}

        # 2) objets JSON concaténés (raw_decode en boucle)
        try:
            decoder = JSONDecoder()
            idx = 0
            length = len(text)
            objs = []
            while idx < length:
                obj, offset = decoder.raw_decode(text, idx)
                objs.append(obj)
                idx += offset
                while idx < length and text[idx].isspace():
                    idx += 1
        except Exception:
            objs = []

        if objs:
            repaired_path = CACHE_FILE + '.repaired.concat.json'
            try:
                with open(repaired_path, 'w', encoding='utf-8') as rf:
                    json.dump(objs, rf, indent=2, ensure_ascii=False)
                print(f"Objets concaténés détectés — version réparée écrite dans {repaired_path}")
            except Exception:
                pass
            return {}

        # 3) tenter de restaurer la sauvegarde .bak si disponible
        bak = CACHE_FILE + '.bak'
        if os.path.exists(bak):
            try:
                with open(bak, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print("Fichier corrompu. Chargement depuis .bak réussi.")
                return data
            except Exception:
                pass

        return {}
    # except Exception as e:
        print(f"Erreur inattendue lors de la lecture du cache : {e}")
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
    with _cache_lock:
        ensure_cache_dir()
        cache_data = load_cache()

        if gh_id in cache_data:
            cache_data[gh_id] = {
                'computed': {},
                'comparison': {},
                'entries': []
            }

        try:
            _write_cache_file(cache_data)
        except Exception as e:
            print(f"Erreur lors de la suppression du cache : {e}")


def clear_all_cache():
    """Vide complètement le cache."""
    with _cache_lock:
        ensure_cache_dir()
        try:
            _write_cache_file({})
        except Exception as e:
            print(f"Erreur lors du vidage du cache : {e}")
