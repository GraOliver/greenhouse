from flask import Flask

from models.database import initialize_database
from views.pages import pages_bp


# Création de l'application Flask et enregistrement des blueprints.
# La base de données est initialisée au démarrage pour s'assurer que
# les tables et les données initiales existent avant toute requête.
def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.register_blueprint(pages_bp)
    initialize_database()
    return app


# Démarrage direct de l'application en mode debug pour le développement.
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
