from src.models import db
from datetime import datetime

class Reporte(db.Model):
    __tablename__ = 'reportes'
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(500), nullable=False)
    nombre_lugar = db.Column(db.String(255), nullable=True)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fotos = db.relationship('FotoReporte', backref='reporte', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'nombre_lugar': self.nombre_lugar,
            'latitud': self.latitud,
            'longitud': self.longitud,
            'fecha_creacion': self.fecha_creacion.isoformat(),
            'fotos': [foto.to_dict() for foto in self.fotos]
        }

class FotoReporte(db.Model):
    __tablename__ = 'fotos_reporte'
    id = db.Column(db.Integer, primary_key=True)
    reporte_id = db.Column(db.Integer, db.ForeignKey('reportes.id'), nullable=False)
    nombre_archivo = db.Column(db.String(255), nullable=False)
    ruta_archivo = db.Column(db.String(500), nullable=False)
    fecha_subida = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'reporte_id': self.reporte_id,
            'nombre_archivo': self.nombre_archivo,
            'ruta_archivo': self.ruta_archivo,
            'fecha_subida': self.fecha_subida.isoformat()
        }


