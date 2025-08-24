# src/models/reporte.py
from src.models import db
from datetime import datetime, timezone

def _iso_utc_z(dt):
    """Devuelve ISO-8601 en UTC con sufijo 'Z' (o None)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

class Reporte(db.Model):
    __tablename__ = 'reportes'

    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(500), nullable=False)
    nombre_lugar = db.Column(db.String(255), nullable=True)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)

    # Fechas en UTC (serializadas con sufijo 'Z' en to_dict)
   fecha_creacion = db.Column(db.DateTime(timezone=True), index=True,
                                default=lambda: datetime.now(timezone.utc))

    # NUEVO: flag de visibilidad para mostrar/ocultar en el mapa
    visible = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # Fotos relacionadas
    fotos = db.relationship(
        'FotoReporte',
        backref='reporte',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def to_dict(self):
        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'nombre_lugar': self.nombre_lugar,
            'latitud': self.latitud,
            'longitud': self.longitud,
            'fecha_creacion': _iso_utc_z(self.fecha_creacion),
            'visible': bool(self.visible),
            'fotos': [foto.to_dict() for foto in self.fotos],
        }

class FotoReporte(db.Model):
    __tablename__ = 'fotos_reporte'

    id = db.Column(db.Integer, primary_key=True)
    reporte_id = db.Column(db.Integer, db.ForeignKey('reportes.id'), nullable=False)
    nombre_archivo = db.Column(db.String(255), nullable=False)
    # Ruta pública relativa a /static (ej: "/uploads/reportes/<uuid>.jpg")
    ruta_archivo = db.Column(db.String(500), nullable=False)
    fecha_subida = db.Column(db.DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'reporte_id': self.reporte_id,
            'nombre_archivo': self.nombre_archivo,
            'ruta_archivo': self.ruta_archivo,
            'fecha_subida': _iso_utc_z(self.fecha_subida),
        }
