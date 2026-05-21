# Processeur pour traiter les données des capteurs
def process_raw_sensor_message(gh_id, comp_id, data):
    """
    Traite les données brutes des capteurs et les formate pour l'affichage.
    Cette fonction peut être étendue pour inclure des conversions d'unités,
    des calculs supplémentaires ou des validations de données.
    """
    processed_data = {}
    for key, value in data.items():
        if isinstance(value, (int, float)):
            processed_data[f"{gh_id}{comp_id}{key.lower()}"] = value
        else:
            processed_data[f"{key.lower()}"] = str(value)
    
    print(f"Données traitées pour serre {gh_id}, compartiment {comp_id} : {processed_data}")
    return processed_data