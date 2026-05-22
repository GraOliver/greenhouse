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
from models.database import get_db_connection


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
        "SELECT temperature_air_min, temperature_air_max, temperature_sol_min, temperature_sol_max, humidite_air_min, humidite_air_max, humidite_sol_min, humidite_sol_max FROM cultures WHERE id = ?",
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


def compare_with_db(averages: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, Any]:
    """Compare les moyennes calculées avec l'historique en BDD et les seuils de culture.

    `averages` attend un dict de la forme : { 'S1': { 'C1': {'ta':val,...}, ... }, ... }

    Retourne un dict structuré contenant les historiques et les décisions recommandées.
    """
    results = {}
    for serre_nom, comps in averages.items():
        results[serre_nom] = {}
        # récupère seuils culture
        thresholds = get_culture_thresholds_for_serre(serre_nom)
        for comp, metrics in comps.items():
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
                    decisions.append(f"{serre_nom}/{comp}: {key} supérieur moyenne historique ({cur_val:.2f} > {hist_val:.2f})")
                # comparaison avec seuils culture si disponibles
                min_key = f"{key}_min"
                max_key = f"{key}_max"
                if thresholds.get(min_key) is not None and thresholds.get(max_key) is not None:
                    if cur_val < thresholds[min_key]:
                        decisions.append(f"{serre_nom}/{comp}: {key} inférieur au seuil min ({cur_val:.2f} < {thresholds[min_key]:.2f})")
                    if cur_val > thresholds[max_key]:
                        decisions.append(f"{serre_nom}/{comp}: {key} supérieur au seuil max ({cur_val:.2f} > {thresholds[max_key]:.2f})")

            results[serre_nom][comp] = {
                "current": metrics,
                "historical": hist,
                "thresholds": thresholds,
                "decisions": decisions,
            }
    return results


def process_raw_sensor_message(gh_id, comp_id, data):
    """Traite un message de capteur et renvoie les moyennes et comparaisons.

    - `gh_id` peut être une chaîne 'S1,S2' ou une liste. Même chose pour `comp_id`.
    - `data` est un dict contenant au moins les clés `ta`, `ts`, `ha`, `hs`.

    La fonction calcule la moyenne pour chaque métrique (si la valeur fournie
    est une liste, on prend la moyenne de la liste; si c'est une valeur simple,
    la moyenne est cette valeur). Puis elle compare avec les données historiques
    en base et produit des recommandations.
    """
    gh_list = normalize_ids(gh_id)
    comp_list = normalize_ids(comp_id)

    # Structure: { 'S1': { 'C1': {'ta':..,'ts':..,'ha':..,'hs':..}, ... }, ... }
    computed: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}

    # Si aucune serre/comp fournie, on tente d'utiliser des valeurs par défaut
    if not gh_list:
        gh_list = ["Unknown"]
    if not comp_list:
        comp_list = ["C1"]

    for gh in gh_list:
        computed.setdefault(gh, {})
        for comp in comp_list:
            # calcule la moyenne pour chaque métrique - accepte list ou scalar
            metrics = {}
            for k in ("ta", "ts", "ha", "hs"):
                v = data.get(k)
                if isinstance(v, list):
                    metrics[k] = calc_average([x for x in v if isinstance(x, (int, float))])
                elif isinstance(v, (int, float)):
                    metrics[k] = float(v)
                else:
                    # essayer de convertir une chaîne numérique
                    try:
                        metrics[k] = float(v)
                    except Exception:
                        metrics[k] = None
            computed[gh][comp] = metrics

    # Compare avec BDD et retourne une structure détaillée
    comparison = compare_with_db(computed)

    # Log pour debug
    print(f"Computed averages: {computed}")
    print(f"Comparison results: {comparison}")

    return {"computed": computed, "comparison": comparison}
