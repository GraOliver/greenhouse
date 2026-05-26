import os
from flask import Flask
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from wtforms import PasswordField
from wtforms.validators import Optional

from models.database import initialize_database
from views.pages import pages_bp
from views.auth import auth_bp
from services.mqtt_service import mqtt_start
from processing.migration import start_migration_scheduler
from models.orm import db, User, Serre, Culture

class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and getattr(current_user, 'is_admin', False)

class UserModelView(SecureModelView):
    """Vue personnalisée pour gérer les utilisateurs avec hachage de mot de passe."""
    column_list = ['username', 'is_admin']
    form_columns = ['username', 'password_hash', 'is_admin']
    
    def scaffold_form(self):
        """Crée un formulaire avec un champ de mot de passe."""
        form_class = super().scaffold_form()
        # Remplace le champ password_hash par un champ de mot de passe
        form_class.password_hash = PasswordField('Mot de passe', validators=[Optional()])
        return form_class
    
    def on_model_change(self, form, model, is_created):
        """Hache le mot de passe avant de sauvegarder."""
        # Récupère la valeur du champ password_hash du formulaire
        password_input = form.password_hash.data
        
        # Si un nouveau mot de passe a été fourni, le hache
        if password_input:
            model.set_password(password_input)
        # Si c'est un nouvel utilisateur et pas de mot de passe fourni, génère une erreur
        elif is_created:
            raise ValueError("Un mot de passe est requis pour créer un nouvel utilisateur")
        
        super().on_model_change(form, model, is_created)

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
    
    with app.app_context():
        initialize_database()
        # Crée les tables SQLAlchemy si elles n'existent pas
        db.create_all()
    
    admin = Admin(app, name='Nsele Admin', url='/admin')
    admin.add_view(UserModelView(User, db.session, name='Utilisateurs'))
    admin.add_view(SecureModelView(Serre, db.session, name='Serres'))
    admin.add_view(SecureModelView(Culture, db.session, name='Cultures'))
    
    mqtt_start()
    start_migration_scheduler()
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
