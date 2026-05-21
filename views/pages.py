"""Module de vues Flask et d'API pour l'application de gestion de serres.

Ce module utilise un blueprint unique pour exposer :
- les routes de rendu HTML des pages principales,
- les routes API JSON nécessaires au frontend JavaScript,
- un flux SSE de démonstration.
"""

import json
import random
import time
from flask import Blueprint, Response, render_template, request, stream_with_context, jsonify

from models.database import get_db_connection
from models.greenhouse import (
    add_compartment,
    create_greenhouse,
    delete_compartment,
    delete_greenhouse,
    get_all_greenhouses,
    get_greenhouse,
    update_greenhouse,
)

# Blueprint principal des pages et des API de l'application.
pages_bp = Blueprint('pages', __name__)


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
def dashboard():
    # Page principale du dashboard.
    # Récupère toutes les serres et les passe au contexte du template.
    greenhouses = get_all_greenhouses()
    return render_template('dashboard.html', greenhouses=greenhouses)


@pages_bp.route('/commande')
def commande():
    # Page des commandes et actions possibles.
    greenhouses = get_all_greenhouses()
    return render_template('commands.html', greenhouses=greenhouses)


@pages_bp.route('/history')
def history_page():
    # Page de l'historique des mesures et événements.
    return render_template('history.html')


@pages_bp.route('/settings')
def settings():
    # Page de configuration des serres et paramètres.
    # Passe la liste des serres et des cultures au template.
    greenhouses = get_all_greenhouses()
    return render_template('settings.html', greenhouses=greenhouses)


@pages_bp.route('/greenhouse/<gh_id>')
def greenhouse_detail(gh_id):
    # Page de détail d'une serre, affichant ses compartiments et seuils.
    greenhouse = get_greenhouse(gh_id)
    if greenhouse is None:
        return render_template('404.html'), 404
    return render_template('greenhouse_detail.html', greenhouse=greenhouse, gh_id=gh_id)


# Routes API JSON utilisées par le frontend JavaScript.
# Elles ne rendent pas de pages HTML, elles exposent des données et actions REST.
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT
            nom AS id,
            description AS name,
            temperature_air_min,
            temperature_air_max,
            temperature_sol_min,
            temperature_sol_max,
            humidite_air_min,
            humidite_air_max,
            humidite_sol_min,
            humidite_sol_max
        FROM cultures
        ORDER BY nom
        '''
    )
    cultures = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(cultures)


@pages_bp.route('/api/stream')
def api_stream():
    # Flux SSE de démonstration qui envoie régulièrement des valeurs moyennes.
    # Ce endpoint peut être étendu ultérieurement vers un vrai flux MQTT / WebSocket.
    def event_stream():
        while True:
            payload = {
                'topic': 'serre/updates/averages',
                'payload': {
                    'TA': round(20.0 + random.random() * 6.0, 1),
                    'TS': round(18.0 + random.random() * 5.0, 1),
                    'HA': round(55.0 + random.random() * 12.0, 1),
                    'HS': round(35.0 + random.random() * 18.0, 1),
                }
            }
            yield f'data: {json.dumps(payload)}\n\n'
            time.sleep(5)

    return Response(stream_with_context(event_stream()), content_type='text/event-stream')
