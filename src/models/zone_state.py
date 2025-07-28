from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ZoneState(db.Model):
    __tablename__ = 'zone_states'
    
    id = db.Column(db.Integer, primary_key=True)
    zone_name = db.Column(db.String(100), nullable=False, unique=True)
    state = db.Column(db.String(20), nullable=False, default='green')  # green, yellow, red
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.String(50), default='admin')
    
    def to_dict(self):
        return {
            'id': self.id,
            'zone_name': self.zone_name,
            'state': self.state,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by': self.updated_by
        }
    
    @staticmethod
    def get_all_states():
        """Obtener todos los estados de las zonas"""
        states = ZoneState.query.all()
        return {state.zone_name: state.to_dict() for state in states}
    
    @staticmethod
    def update_zone_state(zone_name, state, updated_by='admin'):
        """Actualizar el estado de una zona"""
        zone = ZoneState.query.filter_by(zone_name=zone_name).first()
        if zone:
            zone.state = state
            zone.updated_at = datetime.utcnow()
            zone.updated_by = updated_by
        else:
            zone = ZoneState(
                zone_name=zone_name,
                state=state,
                updated_at=datetime.utcnow(),
                updated_by=updated_by
            )
            db.session.add(zone)
        
        db.session.commit()
        return zone.to_dict()

