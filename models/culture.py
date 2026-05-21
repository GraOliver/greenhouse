from models.database import get_db_connection, initialize_database


def _fetch_culture(culture_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cultures WHERE nom = ?", (culture_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_cultures():
    initialize_database()
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
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_culture(culture_id):
    row = _fetch_culture(culture_id)
    if row is None:
        return None
    return {
        'id': row['nom'],
        'name': row['description'] or row['nom'],
        'temperature_air_min': row['temperature_air_min'],
        'temperature_air_max': row['temperature_air_max'],
        'temperature_sol_min': row['temperature_sol_min'],
        'temperature_sol_max': row['temperature_sol_max'],
        'humidite_air_min': row['humidite_air_min'],
        'humidite_air_max': row['humidite_air_max'],
        'humidite_sol_min': row['humidite_sol_min'],
        'humidite_sol_max': row['humidite_sol_max'],
    }


def create_culture(culture_id, name, temperature_sol_min, temperature_sol_max, temperature_air_min, temperature_air_max, humidite_sol_min, humidite_sol_max, humidite_air_min, humidite_air_max):
    initialize_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            INSERT INTO cultures (
                nom, description, temperature_sol_min, temperature_sol_max,
                temperature_air_min, temperature_air_max, humidite_sol_min,
                humidite_sol_max, humidite_air_min, humidite_air_max
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                culture_id,
                name,
                temperature_sol_min,
                temperature_sol_max,
                temperature_air_min,
                temperature_air_max,
                humidite_sol_min,
                humidite_sol_max,
                humidite_air_min,
                humidite_air_max,
            )
        )
        conn.commit()
    except Exception:
        conn.close()
        return None
    conn.close()
    return get_culture(culture_id)


def update_culture(culture_id, update_data):
    initialize_database()
    row = _fetch_culture(culture_id)
    if row is None:
        return None

    updates = []
    params = []

    if 'id' in update_data and update_data['id']:
        updates.append('nom = ?')
        params.append(update_data['id'])
    if 'name' in update_data and update_data['name'] is not None:
        updates.append('description = ?')
        params.append(update_data['name'])
    if 'temperature_sol_min' in update_data:
        updates.append('temperature_sol_min = ?')
        params.append(update_data['temperature_sol_min'])
    if 'temperature_sol_max' in update_data:
        updates.append('temperature_sol_max = ?')
        params.append(update_data['temperature_sol_max'])
    if 'temperature_air_min' in update_data:
        updates.append('temperature_air_min = ?')
        params.append(update_data['temperature_air_min'])
    if 'temperature_air_max' in update_data:
        updates.append('temperature_air_max = ?')
        params.append(update_data['temperature_air_max'])
    if 'humidite_sol_min' in update_data:
        updates.append('humidite_sol_min = ?')
        params.append(update_data['humidite_sol_min'])
    if 'humidite_sol_max' in update_data:
        updates.append('humidite_sol_max = ?')
        params.append(update_data['humidite_sol_max'])
    if 'humidite_air_min' in update_data:
        updates.append('humidite_air_min = ?')
        params.append(update_data['humidite_air_min'])
    if 'humidite_air_max' in update_data:
        updates.append('humidite_air_max = ?')
        params.append(update_data['humidite_air_max'])

    if not updates:
        return get_culture(culture_id)

    params.append(culture_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"UPDATE cultures SET {', '.join(updates)} WHERE nom = ?", params)
        conn.commit()
    except Exception:
        conn.close()
        return None
    conn.close()
    new_id = update_data.get('id', culture_id)
    return get_culture(new_id)


def delete_culture(culture_id):
    initialize_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cultures WHERE nom = ?', (culture_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted
