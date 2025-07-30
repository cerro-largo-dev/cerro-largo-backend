"""
Modelo de usuario de la aplicación.

Importa la instancia `db` desde el paquete `src.models` para
compartir la misma conexión a base de datos en toda la aplicación.
"""

from datetime import datetime

# Importar la instancia global de SQLAlchemy definida en src/models/__init__.py
from . import db

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.username}>'
