from flask_sqlalchemy import SQLAlchemy
from argon2 import PasswordHasher

db = SQLAlchemy()
ph = PasswordHasher()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    nombre = db.Column(db.String(100))
    role = db.Column(db.String(50), nullable=False)  # ADMIN | ALCALDE | OPERADOR
    municipio_id = db.Column(db.String(100), nullable=True)  # requerido si ALCALDE
    password_hash = db.Column(db.String(255), nullable=False)
    force_password_reset = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<User {self.email}>'

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'nombre': self.nombre,
            'role': self.role,
            'municipio_id': self.municipio_id,
            'force_password_reset': self.force_password_reset,
            'is_active': self.is_active
        }

    def set_password(self, password):
        self.password_hash = ph.hash(password)

    def check_password(self, password):
        try:
            return ph.verify(self.password_hash, password)
        except Exception:
            return False


