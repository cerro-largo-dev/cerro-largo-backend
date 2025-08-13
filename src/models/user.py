from . import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'alcalde'
    municipality = db.Column(db.String(100), nullable=True) # For 'alcalde' role
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'municipality': self.municipality,
            'created_at': self.created_at.isoformat()
        }

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
