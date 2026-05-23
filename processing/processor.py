"""Processeur pour traiter les données des capteurs.

Ce module expose plusieurs fonctions :
- `normalize_ids` : accepte une chaîne 'S1,S2' ou une liste et renvoie une liste.
- `calc_average` : calcule la moyenne d'une liste de nombres (robuste aux valeurs vides).
- `fetch_historical_averages` : lit les dernières mesures stockées en base pour une serre.
- `compare_with_db` : compare les moyennes lues avec les valeurs historiques et seuils de la culture.
- `process_raw_sensor_message` : point d'entrée qui normalise l'entrée, calcule les moyennes
  par compartiment/serre, et fait la comparaison.

Les fonctions incluent des commentaires en français comme demandé.
"""

from typing import List, Dict, Any, Optional
from models.database import get_db_connection, create_alert, auto_resolve_alerts

# Variable globale pour stocker la dernière mesure connue de chaque compartiment
# Format: { 'S1': { 'C1': {'ta': 20.0, 'ts': 18.0}, 'C2': {'ta': 21.0, ...} } }
LATEST_COMPARTMENT_DATA = {}


def normalize_ids(ids) -> List[str]:
    """Normalise l'input d'identifiants.

    - Si `ids` est une chaîne de la forme 'S1,S2', on retourne ['S1', 'S2'].
    - Si c'est déjà une liste, on la nettoie (strip) et la retourne.
    - Si c'est une seule valeur non vide, on retourne [str(value)].
    """
    if ids is None:
        return []
    if isinstance(ids, list):
        return [str(i).strip() for i in ids if str(i).strip()]
    if isinstance(ids, str):
        return [s.strip() for s in ids.split(',') if s.strip()]
    return [str(ids).strip()]


def calc_average(values: List[float]) -> Optional[float]:
    """Calcule la moyenne d'une liste de valeurs numériques.

    Retourne `None` si la liste est vide ou si aucune valeur numérique n'est fournie.
    """
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return sum(nums) / len(nums)


def fetch_historical_averages(serre_nom: str, limit: int = 20) -> Dict[str, Optional[float]]:
    """Récupère les moyennes historiques à partir des dernières `limit` mesures pour une serre.

    Renvoie un dictionnaire avec les clés : `ta` (temperature_air), `ts` (temperature_sol),
    `ha` (humidite_air), `hs` (humidite_sol). Les valeurs peuvent être `None` si pas de données.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Récupère l'id de la serre depuis son nom
    cur.execute("SELECT id, culture_id FROM serres WHERE nom = ?", (serre_nom,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"ta": None, "ts": None, "ha": None, "hs": None}

    serre_id = row[0]

    # Récupère les dernières mesures (limit) et calcule la moyenne en Python
    cur.execute(
        "SELECT temperature_air, humidite_air, temperature_sol, humidite_sol FROM mesures WHERE serre_id = ? ORDER BY date_mesure DESC LIMIT ?",
        (serre_id, limit)
    )
    rows = cur.fetchall()
    conn.close()

    tas, hass, tss, hss = [], [], [], []
    for r in rows:
        ta, ha, ts, hs = r
        if isinstance(ta, (int, float)):
            tas.append(ta)
        if isinstance(ha, (int, float)):
            hass.append(ha)
        if isinstance(ts, (int, float)):
            tss.append(ts)
        if isinstance(hs, (int, float)):
            hss.append(hs)

    return {
        "ta": calc_average(tas),
        "ha": calc_average(hass),
        "ts": calc_average(tss),
        "hs": calc_average(hss),
    }


def get_culture_thresholds_for_serre(serre_nom: str) -> Dict[str, Optional[float]]:
    """Récupère les seuils min/max de la culture associée à la serre.

    Retourne un dictionnaire avec les champs min/max pour air et sol.
    Si aucune culture n'est trouvée, retourne des None.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT culture_id FROM serres WHERE nom = ?", (serre_nom,))
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return {}
    culture_id = row[0]

    cur.execute(
        "SELECT temperature_air_min, temperature_air_max, temperature_sol_min, temperature_sol_max, humidite_air_min, humidite_air_max, humidite_sol_min, humidite_sol_max FROM cultures WHERE nom = ?",
        (culture_id,)
    )
    c = cur.fetchone()
    conn.close()
    if not c:
        return {}
    return {
        "ta_min": c[0], "ta_max": c[1],
        "ts_min": c[2], "ts_max": c[3],
        "ha_min": c[4], "ha_max": c[5],
        "hs_min": c[6], "hs_max": c[7],
    }


def compare_with_db(global_averages: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, Any]:
    """Compare la moyenne GLOBALE de la serre avec l'historique en BDD et les seuils de culture.

    `global_averages` attend un dict de la forme : { 'S1': {'ta':val, 'ts':val, ...}, ... }

    Retourne un dict structuré contenant les historiques et les décisions/alertes recommandées.
    """
    results = {}
    for serre_nom, metrics in global_averages.items():
        results[serre_nom] = {}
        # récupère seuils culture
        thresholds = get_culture_thresholds_for_serre(serre_nom)
        hist = fetch_historical_averages(serre_nom)
        decisions = []
        
        # Pour chaque métrique, comparer valeur actuelle, historique et seuils
        for key, label in (("ta", "temperature_air"), ("ts", "temperature_sol"), ("ha", "humidite_air"), ("hs", "humidite_sol")):
            cur_val = metrics.get(key)
            hist_val = hist.get(key)
            
            # comparaison avec historique
            if cur_val is None:
                continue
            if hist_val is not None and cur_val > hist_val:
                decisions.append(f"{serre_nom}: {key} supérieur moyenne historique ({cur_val:.2f} > {hist_val:.2f})")
            
            # comparaison avec seuils culture si disponibles
            min_key = f"{key}_min"
            max_key = f"{key}_max"
            
            # Si nous avons des seuils pour cette métrique
            if thresholds.get(min_key) is not None and thresholds.get(max_key) is not None:
                is_alert = False
                
                # Import local pour éviter l'import circulaire avec mqtt_service
                from services.mqtt_service import publish_actuator_command
                
                if cur_val < thresholds[min_key]:
                    msg = f"La moyenne globale de {label} est trop basse ({cur_val:.1f} < {thresholds[min_key]:.1f})"
                    decisions.append(f"{serre_nom}: {key} inférieur au seuil min")
                    
                    if create_alert(serre_nom, key, msg):
                        # Action automatique si nouvelle alerte créée
                        if key == 'hs':  # Humidité sol basse = allumer pompe
                            publish_actuator_command(serre_nom, 'pump', 'on')
                    is_alert = True
                
                elif cur_val > thresholds[max_key]:
                    msg = f"La moyenne globale de {label} est trop haute ({cur_val:.1f} > {thresholds[max_key]:.1f})"
                    decisions.append(f"{serre_nom}: {key} supérieur au seuil max")
                    
                    if create_alert(serre_nom, key, msg):
                        # Action automatique si nouvelle alerte créée
                        if key == 'ta':  # Température air haute = allumer ventilateur
                            publish_actuator_command(serre_nom, 'cooling', 'on')
                        elif key == 'ts': # Température sol haute = allumer pompe (arrosage) pour rafraîchir
                            publish_actuator_command(serre_nom, 'pump', 'on')
                    is_alert = True
                
                # Si aucune alerte sur cette métrique (valeur normale), on tente une auto-résolution
                if not is_alert:
                    if auto_resolve_alerts(serre_nom, key):
                        # Si une alerte vient d'être résolue, on éteint l'actionneur correspondant
                        if key == 'ta':
                            publish_actuator_command(serre_nom, 'cooling', 'off')
                        elif key == 'hs' or key == 'ts':
                            publish_actuator_command(serre_nom, 'pump', 'off')

        results[serre_nom] = {
            "current": metrics,
            "historical": hist,
            "thresholds": thresholds,
            "decisions": decisions,
        }
    return results


def process_raw_sensor_message(gh_id, comp_id, data):
    """Traite un message de capteur et renvoie la moyenne globale et comparaisons.

    - Met à jour la dernière valeur connue pour le compartiment.
    - Calcule la moyenne globale de la serre (tous compartiments confondus).
    - Compare la moyenne globale avec les seuils de culture pour générer des alertes.
    """
    gh_list = normalize_ids(gh_id)
    comp_list = normalize_ids(comp_id)

    # Si aucune serre/comp fournie, on tente d'utiliser des valeurs par défaut
    if not gh_list:
        gh_list = ["Unknown"]
    if not comp_list:
        comp_list = ["C1"]

    global LATEST_COMPARTMENT_DATA

    for gh in gh_list:
        if gh not in LATEST_COMPARTMENT_DATA:
            LATEST_COMPARTMENT_DATA[gh] = {}
            
        for comp in comp_list:
            # calcule la moyenne pour chaque métrique de ce compartiment spécifique
            metrics = {}
            for k in ("ta", "ts", "ha", "hs"):
                v = data.get(k)
                if isinstance(v, list):
                    metrics[k] = calc_average([x for x in v if isinstance(x, (int, float))])
                elif isinstance(v, (int, float)):
                    metrics[k] = float(v)
                else:
                    try:
                        metrics[k] = float(v)
                    except Exception:
                        metrics[k] = None
                        
            # Enregistrer la dernière valeur pour ce compartiment
            LATEST_COMPARTMENT_DATA[gh][comp] = metrics

    # Calculer la MOYENNE GLOBALE pour chaque serre modifiée
    global_computed = {}
    for gh in gh_list:
        all_comps = LATEST_COMPARTMENT_DATA[gh]
        gh_metrics = {"ta": [], "ts": [], "ha": [], "hs": []}
        
        # Récolter les valeurs de tous les compartiments de cette serre
        for c, m in all_comps.items():
            for k in gh_metrics.keys():
                if m.get(k) is not None:
                    gh_metrics[k].append(m[k])
                    
        # Faire la moyenne globale
        global_computed[gh] = {
            "ta": calc_average(gh_metrics["ta"]),
            "ts": calc_average(gh_metrics["ts"]),
            "ha": calc_average(gh_metrics["ha"]),
            "hs": calc_average(gh_metrics["hs"])
        }

    # Compare la moyenne globale avec la BDD (et génère des alertes globales)
    comparison = compare_with_db(global_computed)

    # Log pour debug
    print(f"Global computed averages: {global_computed}")
    print(f"Comparison results: {comparison}")

    # Pour garder la compatibilité avec le reste du code qui s'attend
    # à un dictionnaire de type {'computed': {'S1': {'C1': {...}, 'C2': {...}}}}
    # on renvoie LATEST_COMPARTMENT_DATA comme 'computed' pour le dashboard,
    # MAIS la 'comparison' contient maintenant la logique de la moyenne globale.
    return {"computed": {gh: LATEST_COMPARTMENT_DATA[gh] for gh in gh_list}, "comparison": comparison}
