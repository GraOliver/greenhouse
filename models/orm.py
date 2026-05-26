from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        """Hache et stocke le mot de passe."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Vérifie si le mot de passe fourni correspond au hash stocké."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Serre(db.Model):
    __tablename__ = 'serres'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    culture_id = db.Column(db.String(100))
    compartiment = db.Column(db.Integer)

    def __repr__(self):
        return self.nom

class Culture(db.Model):
    __tablename__ = 'cultures'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    temperature_sol_min = db.Column(db.Float)
    temperature_sol_max = db.Column(db.Float)
    temperature_air_min = db.Column(db.Float)
    temperature_air_max = db.Column(db.Float)
    humidite_sol_min = db.Column(db.Float)
    humidite_sol_max = db.Column(db.Float)
    humidite_air_min = db.Column(db.Float)
    humidite_air_max = db.Column(db.Float)

    def __repr__(self):
        return self.nom
