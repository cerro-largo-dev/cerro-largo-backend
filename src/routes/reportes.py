import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from src.utils.email_service import EmailService

db = SQLAlchemy()

reportes_bp = Blueprint('reportes', __name__, url_prefix='/api')

# Configuración para subida de archivos
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Modelo Reporte
class Reporte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(255), nullable=False)
    nombre_lugar = db.Column(db.String(255))
    latitud = db.Column(db.Float)
    longitud = db.Column(db.Float)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fotos = db.relationship('FotoReporte', backref='reporte', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'nombre_lugar': self.nombre_lugar,
            'latitud': self.latitud,
            'longitud': self.longitud,
            'fecha_creacion': self.fecha_creacion.isoformat(),
        }

# Modelo FotoReporte
class FotoReporte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporte_id = db.Column(db.Integer, db.ForeignKey('reporte.id'), nullable=False)
    nombre_archivo = db.Column(db.String(255))
    ruta_archivo = db.Column(db.String(255))

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_archivo': self.nombre_archivo,
            'ruta_archivo': self.ruta_archivo,
        }

@reportes_bp.route('/reportes', methods=['POST'])
def crear_reporte():
    try:
        descripcion = request.form.get('descripcion')
        nombre_lugar = request.form.get('nombre_lugar', '')
        latitud = request.form.get('latitud')
        longitud = request.form.get('longitud')

        if not descripcion:
            return jsonify({'error': 'La descripción es obligatoria'}), 400

        try:
            latitud = float(latitud) if latitud else None
            longitud = float(longitud) if longitud else None
            if latitud is not None and (latitud < -90 or latitud > 90):
                return jsonify({'error': 'Latitud fuera de rango'}), 400
            if longitud is not None and (longitud < -180 or longitud > 180):
                return jsonify({'error': 'Longitud fuera de rango'}), 400
        except (ValueError, TypeError):
            latitud = None
            longitud = None

        nuevo_reporte = Reporte(
            descripcion=descripcion,
            nombre_lugar=nombre_lugar if nombre_lugar else None,
            latitud=latitud,
            longitud=longitud
        )

        db.session.add(nuevo_reporte)
        db.session.flush()

        fotos_guardadas = []
        if 'fotos' in request.files:
            fotos = request.files.getlist('fotos')
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'reportes')
            os.makedirs(upload_dir, exist_ok=True)

            for foto in fotos:
                if foto and foto.filename and allowed_file(foto.filename):
                    if len(foto.read()) > MAX_FILE_SIZE:
                        return jsonify({'error': 'El archivo es demasiado grande'}), 400
                    foto.seek(0)

                    extension = foto.filename.rsplit('.', 1)[1].lower()
                    nombre_unico = f"{uuid.uuid4().hex}.{extension}"
                    nombre_seguro = secure_filename(nombre_unico)

                    ruta_archivo = os.path.join(upload_dir, nombre_seguro)
                    foto.save(ruta_archivo)

                    foto_reporte = FotoReporte(
                        reporte_id=nuevo_reporte.id,
                        nombre_archivo=foto.filename,
                        ruta_archivo=f"/uploads/reportes/{nombre_seguro}"
                    )

                    db.session.add(foto_reporte)
                    fotos_guardadas.append(foto_reporte.to_dict())

        db.session.commit()

        try:
            email_service = EmailService()
            reporte_email_data = {
                'descripcion': descripcion,
                'nombre_lugar': nombre_lugar,
                'latitud': latitud,
                'longitud': longitud,
                'fecha_creacion': nuevo_reporte.fecha_creacion.isoformat()
            }
            rutas_fotos = []
            if fotos_guardadas:
                upload_dir = os.path.join(current_app.static_folder, 'uploads', 'reportes')
                for foto in fotos_guardadas:
                    nombre_archivo = foto['ruta_archivo'].split('/')[-1]
                    ruta_completa = os.path.join(upload_dir, nombre_archivo)
                    if os.path.exists(ruta_completa):
                        rutas_fotos.append(ruta_completa)
            email_service.enviar_reporte_ciudadano(reporte_email_data, rutas_fotos)
        except Exception as email_error:
            current_app.logger.error(f"Error al enviar email: {str(email_error)}")

        reporte_dict = nuevo_reporte.to_dict()
        reporte_dict['fotos'] = fotos_guardadas

        return jsonify({
            'mensaje': 'Reporte creado exitosamente',
            'reporte': reporte_dict
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al crear reporte: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500
