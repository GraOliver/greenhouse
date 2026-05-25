import os
from flask import Flask
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user

from models.database import initialize_database
from views.pages import pages_bp
from views.auth import auth_bp
from services.mqtt_service import mqtt_start
from processing.migration import start_migration_scheduler
from models.orm import db, User, Serre, Culture

class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = 'cle_secrete_super_securisee'
    
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'serre.db'))
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    
    initialize_database()
    
    admin = Admin(app, name='Nsele Admin', url='/admin')
    admin.add_view(SecureModelView(User, db.session))
    admin.add_view(SecureModelView(Serre, db.session))
    admin.add_view(SecureModelView(Culture, db.session))
    
    mqtt_start()
    start_migration_scheduler()
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
