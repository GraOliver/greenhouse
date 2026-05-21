from flask import Flask

from models.database import initialize_database
from views.pages import pages_bp
from services.mqtt_service import mqtt_start, on_connect, on_message


# Création de l'application Flask et enregistrement des blueprints.
# La base de données est initialisée au démarrage pour s'assurer que
# les tables et les données initiales existent avant toute requête.
def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.register_blueprint(pages_bp)
    initialize_database()
    mqtt_start()  # Démarrer le service MQTT après le lancement de Flask
    return app


# Crée l'application une seule fois afin que `flask run` fonctionne aussi.
app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
   
