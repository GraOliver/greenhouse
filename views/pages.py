"""Module de vues Flask et d'API pour l'application de gestion de serres.

Ce module utilise un blueprint unique pour exposer :
- les routes de rendu HTML des pages principales,
- les routes API JSON nécessaires au frontend JavaScript,
- un flux SSE de démonstration.
"""

import json
import random
import time
import re
import unicodedata
from flask import Blueprint, Response, render_template, request, stream_with_context, jsonify, redirect, url_for
from flask_login import login_required

from services.mqtt_service import publish_actuator_command
from models.database import (
    get_db_connection, 
    save_history_event, 
    get_active_alerts, 
    resolve_alert
)
from models.greenhouse import (
    add_compartment,
    create_greenhouse,
    delete_compartment,
    delete_greenhouse,
    get_all_greenhouses,
    get_greenhouse,
    update_greenhouse,
)
from models.culture import get_culture
from models.culture import (
    create_culture,
    get_all_cultures,
    get_culture,
    update_culture,
    delete_culture,
)
from services.mqtt_service import get_sensor_data, register_listener, unregister_listener
from processing.cache import get_cache_data, get_cache_entries

# Blueprint principal des pages et des API de l'application.
pages_bp = Blueprint('pages', __name__)


def slugify(value: str) -> str: # Convertit une chaîne en un slug URL-friendly (ex: "Tomate Cerise" -> "tomate-cerise").
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower().strip()
    normalized = re.sub(r'[^a-z0-9]+', '-', normalized)
    normalized = re.sub(r'-+', '-', normalized).strip('-')
    return normalized or value.lower().replace(' ', '-')


def _build_placeholder_state(greenhouse):
    # Génère des données factices pour le dashboard et le flux SSE
    # lorsque les données réelles des capteurs ne sont pas encore disponibles.
    compartments = greenhouse.get('compartments', [])
    sensor_data = {}
    total = {'TA': 0.0, 'TS': 0.0, 'HA': 0.0, 'HS': 0.0}
    count = 0

    for comp in compartments:
        values = {
            'TA': round(20.0 + random.random() * 6.0, 1),
            'TS': round(18.0 + random.random() * 5.0, 1),
            'HA': round(55.0 + random.random() * 12.0, 1),
            'HS': round(35.0 + random.random() * 18.0, 1),
        }
        sensor_data[comp] = values
        for key in values:
            total[key] += values[key]
        count += 1

    averages = {key: round(total[key] / count, 1) if count else 0.0 for key in total}
    history = [
        {
            'time': f'{hour:02d}:00',
            'TA': round(20.0 + random.random() * 6.0, 1),
            'TS': round(18.0 + random.random() * 5.0, 1),
            'HA': round(55.0 + random.random() * 12.0, 1),
            'HS': round(35.0 + random.random() * 18.0, 1),
        }
        for hour in range(8, 16)
    ]

    return {
        'sensor_data': sensor_data,
        'averages': averages,
        'history': history,
    }


# Routes de rendu des pages HTML du site.
# Ces routes renvoient des templates Jinja destinés à être vus directement
# par l'utilisateur via un navigateur.
@pages_bp.route('/')
@login_required
def dashboard():
    # Page principale du dashboard.
    # Récupère toutes les serres depuis la base de données.
    greenhouses = get_all_greenhouses()
    selected_greenhouse = greenhouses[0] if greenhouses else None
    return render_template(
        'dashboard.html',
        greenhouses=greenhouses,
        selected_greenhouse=selected_greenhouse
    )


@pages_bp.route('/commande')
@login_required
def commande():
    # Page des commandes et actions possibles.
    greenhouses = get_all_greenhouses()
    return render_template('commands.html', greenhouses=greenhouses)


@pages_bp.route('/history')
@login_required
def history_page():
    # Page de l'historique des mesures et événements.
    greenhouses = get_all_greenhouses()
    return render_template('history.html', greenhouses=greenhouses)


@pages_bp.route('/settings')
@login_required
def settings():
    # Page de configuration des serres et paramètres.
    # Passe la liste des serres et des cultures au template.
    greenhouses = get_all_greenhouses()
    cultures = get_all_cultures()
    return render_template('settings.html', greenhouses=greenhouses, cultures=cultures)


@pages_bp.route('/settings/culture', methods=['POST'])
def settings_save_culture():
    form = request.form
    selected_culture = form.get('culture-selector')
    culture_name = form.get('culture-name', '').strip()

    if not culture_name:
        return redirect(url_for('pages.settings'))

    culture_id = slugify(culture_name)
    payload = {
        'id': culture_id,
        'name': culture_name,
        'temperature_sol_min': float(form.get('min-temp-sol', 0)),
        'temperature_sol_max': float(form.get('max-temp-sol', 0)),
        'temperature_air_min': float(form.get('min-temp-air', 0)),
        'temperature_air_max': float(form.get('max-temp-air', 0)),
        'humidite_sol_min': float(form.get('min-hum-sol', 0)),
        'humidite_sol_max': float(form.get('max-hum-sol', 0)),
        'humidite_air_min': float(form.get('min-hum-air', 0)),
        'humidite_air_max': float(form.get('max-hum-air', 0)),
    }

    if selected_culture and selected_culture != 'NEW':
        update_culture(selected_culture, payload)
    else:
        create_culture(**payload)

    return redirect(url_for('pages.settings'))


@pages_bp.route('/settings/greenhouse', methods=['POST'])
def settings_create_greenhouse():   # Route pour créer une nouvelle serre depuis la page de paramètres.
    form = request.form
    gh_name = form.get('gh-name-input', '').strip()
    gh_desc = form.get('gh-description-input', '').strip()
    culture_id = form.get('gh-culture-select', '').strip()

    if gh_name and culture_id:
        gh_id = slugify(gh_name).upper()
        create_greenhouse(gh_id, gh_desc or gh_name, culture_id)

    return redirect(url_for('pages.settings'))


@pages_bp.route('/settings/assign-culture', methods=['POST'])
def settings_assign_culture():
    print(f"information setting {form.request}")
    form = request.form
    greenhouse_id = form.get('assign-gh-select', '').strip()
    culture_id = form.get('assign-culture-select', '').strip()

    if greenhouse_id and culture_id:
        update_greenhouse(greenhouse_id, {'culture': culture_id})

    return redirect(url_for('pages.settings'))

@pages_bp.route('/settings/delete-greenhouse/<gh_id>', methods=['GET'])
def delete_greenhouse_settings(gh_id):
    """Supprime un enregistrement de serre depuis la page de paramètres."""
    delete_greenhouse(gh_id)
    return redirect(url_for('pages.settings'))


@pages_bp.route('/greenhouse/<gh_id>')
def greenhouse_detail(gh_id):
    # Page de détail d'une serre, affichant ses compartiments et seuils.
    greenhouse = get_greenhouse(gh_id)
    if greenhouse is None:
        return render_template('404.html'), 404
    culture = get_culture(greenhouse['culture_id']) if greenhouse.get('culture_id') else None
    return render_template('greenhouse_detail.html', greenhouse=greenhouse, culture=culture, gh_id=gh_id)


@pages_bp.route('/greenhouse/<gh_id>/delete', methods=['GET'])
def delete_greenhouse_view(gh_id):
    """
    Route de suppression d'une serre.
    Appelée par le bouton '🗑️ Supprimer la Serre' dans greenhouse_detail.html.
    Supprime la serre et tous ses compartiments de la base SQLite,
    puis redirige l'utilisateur vers la page des paramètres.
    """
    # Supprimer la serre via la fonction du modèle (inclut la suppression des compartiments associés)
    delete_greenhouse(gh_id)
    # Rediriger vers les paramètres après suppression réussie
    return redirect(url_for('pages.settings'))


# Routes API JSON utilisées par le frontend JavaScript.
# Elles ne rendent pas de pages HTML, elles exposent des données et actions REST.


@pages_bp.route('/api/greenhouses/<gh_id>/actuate', methods=['POST'])
def api_actuate_greenhouse(gh_id):
    """
    Endpoint API pour envoyer une commande manuelle à un actionneur de la serre.
    Reçoit un payload JSON avec l'actionneur et l'état souhaité (ex: {'actuator': 'pump', 'action': 'on'}).
    """
    payload = request.get_json(force=True, silent=True) or {}
    actuator = payload.get('actuator')
    action = payload.get('action')

    if not actuator or not action:
        return jsonify({'error': 'L\'actionneur et l\'action sont requis'}), 400

    # Valider le type d'actionneur et l'action
    if actuator not in ['pump', 'cooling'] or action not in ['on', 'off']:
        return jsonify({'error': 'Actionneur ou action invalide'}), 400

    # Publier la commande MQTT
    success = publish_actuator_command(gh_id, actuator, action)
    if not success:
        return jsonify({'error': 'Échec de l\'envoi de la commande MQTT'}), 500

    # Sauvegarder cet événement d'actionneur manuel dans l'historique SQLite
    details = f"Actionneur '{actuator.upper()}' mis sur '{action.upper()}' (Manuel)"
    save_history_event(gh_id, '--', 'actionneur', details)

    return jsonify({
        'message': f"Commande '{action.upper()}' envoyée avec succès à l'actionneur '{actuator}' de la serre '{gh_id}'."
    }), 200

@pages_bp.route('/api/history', methods=['GET'])
def api_get_history():
    """
    Récupère le journal d'historique depuis la base de données SQLite.
    Filtres optionnels passés en paramètres de requête (GET query parameters) :
    - serre : l'identifiant de la serre (ex: 'S1')
    - type : le type d'événement ('capteur' ou 'actionneur')
    - limit : le nombre max de lignes à retourner (défaut: 200)
    """
    serre_filter = request.args.get('serre', '').strip()
    type_filter = request.args.get('type', '').strip()
    limit_val = request.args.get('limit', '200')

    # Valider la limite pour éviter des injections SQL ou des surcharges
    try:
        limit = int(limit_val)
        if limit <= 0 or limit > 1000:
            limit = 200
    except ValueError:
        limit = 200

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT id, date_heure, serre_id, compartiment, type_event, details FROM history_logs"
    conditions = []
    params = []

    if serre_filter:
        conditions.append("serre_id = ?")
        params.append(serre_filter.upper())
    
    if type_filter:
        conditions.append("type_event = ?")
        params.append(type_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # Trier par date décroissante (plus récent d'abord)
    query += " ORDER BY date_heure DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logs = []
    for row in rows:
        logs.append({
            'id': row['id'],
            'date_heure': row['date_heure'],
            'serre_id': row['serre_id'],
            'compartiment': row['compartiment'],
            'type_event': row['type_event'],
            'details': row['details']
        })

    return jsonify(logs)


@pages_bp.route('/api/history/clear', methods=['POST'])
def api_clear_history():
    """
    Vide complètement le journal d'historique de la base de données SQLite.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history_logs")
        conn.commit()
        conn.close()
        return jsonify({'message': 'Historique vidé avec succès !'}), 200
    except Exception as e:
        print(f"Erreur lors de la suppression de l'historique : {e}")
        return jsonify({'error': 'Impossible de vider l\'historique.'}), 500

@pages_bp.route('/api/greenhouses', methods=['GET'])
def api_get_greenhouses():
    return jsonify(get_all_greenhouses())


@pages_bp.route('/api/greenhouses', methods=['POST']) # Création d'une nouvelle serre via l'API REST.
def api_create_greenhouse():
    payload = request.get_json(force=True, silent=True) or {}
    gh_id = payload.get('id') or payload.get('name')
    name = payload.get('name')
    culture_id = payload.get('culture') or payload.get('culture_id')

    if not gh_id or not name or not culture_id:
        return jsonify({'error': 'id, name et culture sont requis'}), 400

    gh_id = slugify(gh_id).upper()
    greenhouse = create_greenhouse(gh_id, name, culture_id)
    if greenhouse is None:
        return jsonify({'error': 'Une serre portant ce nom existe déjà'}), 409

    return jsonify(greenhouse), 201


@pages_bp.route('/api/greenhouses/<gh_id>', methods=['GET'])
def api_get_greenhouse(gh_id):
    greenhouse = get_greenhouse(gh_id)
    if greenhouse is None:
        return jsonify({'error': 'Serre introuvable'}), 404
    return jsonify(greenhouse)


@pages_bp.route('/api/greenhouses/<gh_id>', methods=['PUT'])
def api_update_greenhouse(gh_id):
    payload = request.get_json(force=True, silent=True) or {}
    greenhouse = update_greenhouse(gh_id, payload)
    if greenhouse is None:
        return jsonify({'error': 'Serre introuvable'}), 404
    return jsonify(greenhouse)




@pages_bp.route('/api/greenhouses/<gh_id>', methods=['DELETE'])
def api_delete_greenhouse(gh_id):
    deleted = delete_greenhouse(gh_id)
    if not deleted:
        return jsonify({'error': 'Serre introuvable'}), 404
    return jsonify({'message': 'Serre supprimée'})


@pages_bp.route('/api/greenhouses/<gh_id>/compartments', methods=['POST'])
def api_add_compartment(gh_id):
    payload = request.get_json(force=True, silent=True) or {}
    comp_id = payload.get('id') or payload.get('compartment')
    if not comp_id:
        return jsonify({'error': 'Identifiant du compartiment requis'}), 400

    if add_compartment(gh_id, comp_id) is False:
        return jsonify({'error': 'Impossible d’ajouter ce compartiment'}), 400
    return jsonify({'message': 'Compartiment ajouté'})


@pages_bp.route('/api/greenhouses/<gh_id>/compartments/<comp_id>', methods=['DELETE'])
def api_delete_compartment(gh_id, comp_id):
    if delete_compartment(gh_id, comp_id) is False:
        return jsonify({'error': 'Compartiment introuvable ou impossible à supprimer'}), 404
    return jsonify({'message': 'Compartiment supprimé'})


@pages_bp.route('/api/greenhouses/<gh_id>/latest-state')
def api_greenhouse_latest_state(gh_id):
    greenhouse = get_greenhouse(gh_id)
    if greenhouse is None:
        return jsonify({'error': 'Serre introuvable'}), 404
    return jsonify(_build_placeholder_state(greenhouse))


@pages_bp.route('/api/cultures')
def api_cultures():
    # Retourne toutes les cultures existantes pour alimenter les formulaires
    # et afficher les seuils sur la page de détail de la serre.
    return jsonify(get_all_cultures())


@pages_bp.route('/api/stream')
def api_stream():
    # Endpoint SSE réel : s'abonne à la queue du service MQTT et renvoie les messages
    def event_stream():
        q = register_listener()
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                except Exception:
                    # envoyer un keep-alive pour éviter que la connexion ne tombe
                    yield ':\n\n'
                    continue

                try:
                    yield f"data: {json.dumps(msg)}\n\n"
                except Exception:
                    # Ignore serialization errors per-message
                    continue
        finally:
            unregister_listener(q)

    return Response(stream_with_context(event_stream()), content_type='text/event-stream')


@pages_bp.route('/api/sensor-data/<gh_id>')
def api_sensor_data(gh_id):
    """API pour récupérer les données calculées (moyennes, comparaison avec seuils) d'une serre.

    Charge d'abord les données en mémoire (mqtt_service), puis du cache JSON si nécessaire.
    Retourne un dictionnaire contenant :
    - computed : moyennes calculées par compartiment {'C1': {'ta': 12.0, ...}, ...}
    - comparison : résultats de la comparaison avec l'historique et les seuils
    - compartments : liste des compartiments de la serre
    - timestamp : moment du dernier calcul
    - entries : historique des dernières entrées du cache (pour graphiques)
    """
    greenhouse = get_greenhouse(gh_id)
    
    # D'abord, essayer de récupérer les données en mémoire (plus récentes)
    sensor_data = get_sensor_data(gh_id)
    
    response = {
        'compartments': greenhouse['compartments'] if greenhouse else [],
        'computed': {},
        'comparison': {},
        'timestamp': None,
        'entries': []
    }

    if sensor_data is not None:
        # Données disponibles en mémoire
        response.update(sensor_data)
    else:
        # Sinon, charger du cache JSON (pour survie aux refreshes de page)
        cache_data = get_cache_data(gh_id)
        if cache_data and cache_data.get('computed'):
            response['computed'] = cache_data.get('computed', {})
            response['comparison'] = cache_data.get('comparison', {})
        else:
            response['error'] = f'Aucune donnée de capteur disponible pour la serre {gh_id}'
    
    # Charger l'historique du cache pour les graphiques
    cache_entries = get_cache_entries(gh_id, limit=100)
    if cache_entries:
        response['entries'] = cache_entries

    return jsonify(response)


# ==========================================
# ROUTES API POUR LES ALERTES GLOBALES
# ==========================================

@pages_bp.route('/api/alerts', methods=['GET'])
def api_get_alerts():
    """
    Récupère toutes les alertes actives.
    On peut filtrer par serre avec le paramètre ?serre_id=S1
    """
    serre_id = request.args.get('serre_id')
    alerts = get_active_alerts(serre_id)
    return jsonify(alerts), 200

@pages_bp.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
def api_resolve_alert(alert_id):
    """
    Marque une alerte comme résolue manuellement par l'utilisateur.
    """
    success = resolve_alert(alert_id)
    if success:
        return jsonify({'message': 'Alerte résolue avec succès'}), 200
    else:
        return jsonify({'error': 'Impossible de résoudre l\'alerte'}), 500
