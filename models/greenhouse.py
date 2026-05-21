import sqlite3
from models.db import load_data
from models.database import get_db_connection, initialize_database

# Ce module gère les opérations CRUD des serres dans la base SQLite.
# Le JSON est conservé uniquement pour l'initialisation.


def _get_culture_display_name(culture_id: str) -> str:
    """Retourne le nom lisible de la culture depuis SQLite."""
    if not culture_id:
        return ''
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT description FROM cultures WHERE nom = ?", (culture_id,))
    row = cursor.fetchone()
    conn.close()
    return row['description'] if row and row['description'] else culture_id


def _get_compartments_for_greenhouse(gh_id: str) -> list:
    """Récupère les compartiments enregistrés pour une serre."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT compartment FROM serre_compartments WHERE serre_nom = ? ORDER BY compartment", (gh_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row['compartment'] for row in rows] if rows else ["C1", "C2", "C3", "C4"]


def get_all_greenhouses():
    """Récupère toutes les serres depuis la base SQLite."""
    initialize_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nom, description, culture_id FROM serres ORDER BY nom")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        culture_id = row['culture_id']
        result.append({
            'id': row['nom'],
            'name': row['description'] or row['nom'],
            'culture': _get_culture_display_name(culture_id),
            'culture_id': culture_id,
            'status': 'OK',
            'compartments': _get_compartments_for_greenhouse(row['nom'])
        })
    return result


def _fetch_greenhouse(gh_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nom, description, culture_id FROM serres WHERE nom = ?", (gh_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_greenhouse(gh_id):
    # Retourne les informations d'une serre sous forme d'objet JSON
    # prêt à être renvoyé par l'API ou utilisé dans une vue.
    row = _fetch_greenhouse(gh_id)
    if row is None:
        return None
    return {
        'id': row['nom'],
        'name': row['description'] or row['nom'],
        'culture': _get_culture_display_name(row['culture_id']),
        'culture_id': row['culture_id'],
        'status': 'OK',
        'compartments': _get_compartments_for_greenhouse(row['nom'])
    }


def create_greenhouse(gh_id, name, culture_id):
    """Crée une nouvelle serre dans la base SQLite."""
    initialize_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM serres WHERE nom = ?", (gh_id,))
    if cursor.fetchone() is not None:
        conn.close()
        return None

    cursor.execute(
        "INSERT INTO serres (nom, description, culture_id, compartiment) VALUES (?, ?, ?, ?)",
        (gh_id, name, culture_id, 4)
    )
    for comp in ["C1", "C2", "C3", "C4"]:
        cursor.execute(
            "INSERT OR IGNORE INTO serre_compartments (serre_nom, compartment) VALUES (?, ?)",
            (gh_id, comp)
        )
    conn.commit()
    conn.close()

    return {
        'id': gh_id,
        'name': name,
        'culture': _get_culture_display_name(culture_id),
        'culture_id': culture_id,
        'status': 'OK',
        'compartments': ["C1", "C2", "C3", "C4"]
    }


def update_greenhouse(gh_id, update_data):
    """Met à jour le nom ou la culture d'une serre existante."""
    initialize_database()
    row = _fetch_greenhouse(gh_id)
    if row is None:
        return None

    updates = []
    params = []
    if 'culture' in update_data:
        updates.append('culture_id = ?')
        params.append(update_data['culture'])
    if 'name' in update_data:
        updates.append('description = ?')
        params.append(update_data['name'])
    if not updates:
        return {
            'id': row['nom'],
            'name': row['description'] or row['nom'],
            'culture': _get_culture_display_name(row['culture_id']),
            'culture_id': row['culture_id'],
            'status': 'OK',
            'compartments': _get_compartments_for_greenhouse(row['nom'])
        }

    params.append(gh_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE serres SET {', '.join(updates)} WHERE nom = ?", params)
    conn.commit()
    conn.close()

    updated = _fetch_greenhouse(gh_id)
    return {
        'id': updated['nom'],
        'name': updated['description'] or updated['nom'],
        'culture': _get_culture_display_name(updated['culture_id']),
        'culture_id': updated['culture_id'],
        'status': 'OK',
        'compartments': _get_compartments_for_greenhouse(updated['nom'])
    }


def delete_greenhouse(gh_id):
    """Supprime une serre et ses compartiments associés."""
    initialize_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM serre_compartments WHERE serre_nom = ?", (gh_id,))
    cursor.execute("DELETE FROM serres WHERE nom = ?", (gh_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def add_compartment(gh_id, comp_id):
    """Ajoute un compartiment à une serre."""
    initialize_database()
    comp_id = comp_id.upper().strip()
    if not comp_id:
        return False

    if _fetch_greenhouse(gh_id) is None:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM serre_compartments WHERE serre_nom = ? AND compartment = ?", (gh_id, comp_id))
    if cursor.fetchone() is not None:
        conn.close()
        return False

    cursor.execute("INSERT INTO serre_compartments (serre_nom, compartment) VALUES (?, ?)", (gh_id, comp_id))
    cursor.execute("UPDATE serres SET compartiment = (SELECT COUNT(*) FROM serre_compartments WHERE serre_nom = ?) WHERE nom = ?", (gh_id, gh_id))
    conn.commit()
    conn.close()
    return True


def delete_compartment(gh_id, comp_id):
    """Supprime un compartiment d'une serre."""
    initialize_database()
    comp_id = comp_id.upper().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM serre_compartments WHERE serre_nom = ? AND compartment = ?", (gh_id, comp_id))
    deleted = cursor.rowcount > 0
    if deleted:
        cursor.execute("UPDATE serres SET compartiment = (SELECT COUNT(*) FROM serre_compartments WHERE serre_nom = ?) WHERE nom = ?", (gh_id, gh_id))
    conn.commit()
    conn.close()
    return deleted
