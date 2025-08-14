from src.models import db  # ✅ usar la instancia global, NO crear otra
from argon2 import PasswordHasher

# Hasher global que usan rutas y seeds
ph = PasswordHasher()


class User(db.Model):
    __tablename__ = 'user'  # mantener nombre por compatibilidad con tu DB actual
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    nombre = db.Column(db.String(100))
    role = db.Column(db.String(50), nullable=False)  # ADMIN | ALCALDE | OPERADOR
    municipio_id = db.Column(db.String(100), nullable=True)  # requerido si ALCALDE
    password_hash = db.Column(db.String(255), nullable=False)
    force_password_reset = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self) -> str:
        return f'<User {self.email}>'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'email': self.email,
            'nombre': self.nombre,
            'role': self.role,
            'municipio_id': self.municipio_id,
            'force_password_reset': self.force_password_reset,
            'is_active': self.is_active,
        }

    # ===== Password helpers (Argon2) =====
    def set_password(self, password: str) -> None:
        self.password_hash = ph.hash(password)

    def check_password(self, password: str) -> bool:
        try:
            return ph.verify(self.password_hash, password)
        except Exception:
            # hash corrupto / esquema distinto / etc.
            return False
