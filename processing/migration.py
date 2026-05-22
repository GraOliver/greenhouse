"""Module de migration des données du cache JSON vers la base de données.

Toutes les heures, les données calculées sont migrées du cache JSON vers la table
mesures_calculees de la base de données.
"""

import threading
import time
from datetime import datetime
from models.database import get_db_connection
from processing.cache import load_cache, clear_cache_for_serre


def migrate_cache_to_database():
    """Migre toutes les données du cache JSON vers la base de données."""
    try:
        cache_data = load_cache()
        
        if not cache_data:
            print("[Migration] Aucune donnée en cache à migrer.")
            return
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        migrated_count = 0
        
        for gh_id, gh_cache in cache_data.items():
            entries = gh_cache.get('entries', [])
            
            if not entries:
                continue
            
            # Insérer les entrées dans la BDD
            for entry in entries:
                computed = entry.get('computed', {})
                
                # Pour chaque compartiment dans les données calculées
                if gh_id in computed:
                    for comp_id, metrics in computed[gh_id].items():
                        try:
                            cur.execute(
                                """INSERT INTO mesures_calculees 
                                (serre_nom, compartment, temperature_air_moy, temperature_sol_moy, humidite_air_moy, humidite_sol_moy, date_mesure)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    gh_id,
                                    comp_id,
                                    metrics.get('ta'),
                                    metrics.get('ts'),
                                    metrics.get('ha'),
                                    metrics.get('hs'),
                                    entry.get('datetime', datetime.now().isoformat())
                                )
                            )
                            migrated_count += 1
                        except Exception as e:
                            print(f"[Migration] Erreur lors de l'insertion : {e}")
            
            # Vider le cache pour cette serre après migration
            clear_cache_for_serre(gh_id)
        
        conn.commit()
        conn.close()
        
        print(f"[Migration] {migrated_count} entrées migrées vers la base de données.")
        
    except Exception as e:
        print(f"[Migration] Erreur lors de la migration : {e}")


def start_migration_scheduler():
    """Démarre un thread qui lance la migration toutes les heures."""
    def scheduler_loop():
        while True:
            # Attendre 1 heure
            time.sleep(3600)
            print(f"[Migration] Début de la migration programmée à {datetime.now()}")
            migrate_cache_to_database()
    
    # Lancer le scheduler dans un thread daemon
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    print("[Migration] Scheduler démarré - migration toutes les heures")


def manual_migrate_now():
    """Force une migration immédiate (utile pour les tests ou les demandes manuelles)."""
    print("[Migration] Migration manuelle démarrée...")
    migrate_cache_to_database()
    print("[Migration] Migration manuelle terminée.")
