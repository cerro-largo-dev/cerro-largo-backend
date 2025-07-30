"""
Modelo que almacena el estado de cada zona o municipio.

Se importa la instancia global `db` desde el paquete `src.models`
en lugar de desde `user` para evitar instanciar SQLAlchemy
múltiples veces.  Todos los modelos deben usar la misma
instancia de `db`.
"""

from . import db
from datetime import datetime

class ZoneState(db.Model):
    __tablename__ = 'zone_states'
    
    id = db.Column(db.Integer, primary_key=True)
    zone_name = db.Column(db.String(100), unique=True, nullable=False)
    state = db.Column(db.String(20), nullable=False, default='green')  # green, yellow, red
    updated_by = db.Column(db.String(100), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'zone_name': self.zone_name,
            'state': self.state,
            'updated_by': self.updated_by,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'notes': self.notes
        }
    
    @staticmethod
    def get_all_states():
        """Obtener todos los estados de zonas como diccionario"""
        zones = ZoneState.query.all()
        result = {}
        for zone in zones:
            result[zone.zone_name] = {
                'state': zone.state,
                'updated_by': zone.updated_by,
                'updated_at': zone.updated_at.isoformat() if zone.updated_at else None,
                'notes': zone.notes
            }
        return result
    
    @staticmethod
    def update_zone_state(zone_name, state, updated_by=None, notes=None):
        """Actualizar o crear el estado de una zona"""
        zone = ZoneState.query.filter_by(zone_name=zone_name).first()
        if zone:
            zone.state = state
            zone.updated_by = updated_by
            zone.updated_at = datetime.utcnow()
            zone.notes = notes
        else:
            zone = ZoneState(
                zone_name=zone_name,
                state=state,
                updated_by=updated_by,
                notes=notes
            )
            db.session.add(zone)
        
        db.session.commit()
        return zone
    
    def __repr__(self):
        return f'<ZoneState {self.zone_name}: {self.state}>'
