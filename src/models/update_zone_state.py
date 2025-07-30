from .user import db
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
    def update_zone_state(zone_name, state, updated_by=None, notes=None) -> dict:
        """
        Actualizar o crear el estado de una zona.

        Este método busca una instancia de ``ZoneState`` con el nombre de zona
        proporcionado. Si existe, actualiza sus campos; si no existe, crea una
        nueva instancia y la agrega a la sesión. Tras hacer ``commit`` en la
        base de datos, se devuelve un diccionario serializable con los datos de
        la zona. Devolver un ``dict`` en lugar de un modelo evita problemas
        de serialización JSON en las vistas que consumen este método.
        """
        zone = ZoneState.query.filter_by(zone_name=zone_name).first()
        if zone:
            # Actualizar campos existentes
            zone.state = state
            zone.updated_by = updated_by
            zone.updated_at = datetime.utcnow()
            zone.notes = notes
        else:
            # Crear una nueva instancia si la zona no existe
            zone = ZoneState(
                zone_name=zone_name,
                state=state,
                updated_by=updated_by,
                notes=notes
            )
            db.session.add(zone)

        # Confirmar cambios en la base de datos
        db.session.commit()

        # Devolver un diccionario para facilitar la serialización JSON
        return zone.to_dict()
    
    def __repr__(self):
        return f'<ZoneState {self.zone_name}: {self.state}>'
