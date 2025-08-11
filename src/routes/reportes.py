import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from src.models.reportes import db, Reporte, FotoReporte
from src.utils.email_service import EmailService

reportes_bp = Blueprint('reportes', __name__)

# Configuración para subida de archivos
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@reportes_bp.route('/reportes', methods=['POST'])
def crear_reporte():
    try:
        # Obtener datos del formulario
        descripcion = request.form.get('descripcion')
        nombre_lugar = request.form.get('nombre_lugar', '')
        latitud = request.form.get('latitud')
        longitud = request.form.get('longitud')
        
        # Validar datos obligatorios
        if not descripcion:
            return jsonify({'error': 'La descripción es obligatoria'}), 400
        
        # Convertir coordenadas a float si están presentes
        try:
            latitud = float(latitud) if latitud else None
            longitud = float(longitud) if longitud else None
        except (ValueError, TypeError):
            latitud = None
            longitud = None
        
        # Crear el reporte
        nuevo_reporte = Reporte(
            descripcion=descripcion,
            nombre_lugar=nombre_lugar if nombre_lugar else None,
            latitud=latitud,
            longitud=longitud
        )
        
        db.session.add(nuevo_reporte)
        db.session.flush()  # Para obtener el ID del reporte
        
        # Procesar archivos de fotos
        fotos_guardadas = []
        if 'fotos' in request.files:
            fotos = request.files.getlist('fotos')
            
            # Crear directorio de uploads si no existe
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'reportes')
            os.makedirs(upload_dir, exist_ok=True)
            
            for foto in fotos:
                if foto and foto.filename and allowed_file(foto.filename):
                    # Generar nombre único para el archivo
                    extension = foto.filename.rsplit('.', 1)[1].lower()
                    nombre_unico = f"{uuid.uuid4().hex}.{extension}"
                    nombre_seguro = secure_filename(nombre_unico)
                    
                    # Guardar archivo
                    ruta_archivo = os.path.join(upload_dir, nombre_seguro)
                    foto.save(ruta_archivo)
                    
                    # Crear registro en la base de datos
                    foto_reporte = FotoReporte(
                        reporte_id=nuevo_reporte.id,
                        nombre_archivo=foto.filename,
                        ruta_archivo=f"/uploads/reportes/{nombre_seguro}"
                    )
                    
                    db.session.add(foto_reporte)
                    fotos_guardadas.append(foto_reporte.to_dict())
        
        # Confirmar transacción
        db.session.commit()
        
        # Enviar reporte por email
        try:
            email_service = EmailService()
            
            # Preparar datos del reporte para el email
            reporte_email_data = {
                'descripcion': descripcion,
                'nombre_lugar': nombre_lugar,
                'latitud': latitud,
                'longitud': longitud,
                'fecha_creacion': nuevo_reporte.fecha_creacion.isoformat()
            }
            
            # Preparar rutas de fotos para adjuntar
            rutas_fotos = []
            if fotos_guardadas:
                upload_dir = os.path.join(current_app.static_folder, 'uploads', 'reportes')
                for foto in fotos_guardadas:
                    # Extraer nombre del archivo de la ruta
                    nombre_archivo = foto['ruta_archivo'].split('/')[-1]
                    ruta_completa = os.path.join(upload_dir, nombre_archivo)
                    if os.path.exists(ruta_completa):
                        rutas_fotos.append(ruta_completa)
            
            # Enviar email
            email_enviado = email_service.enviar_reporte_ciudadano(reporte_email_data, rutas_fotos)
            
            if email_enviado:
                current_app.logger.info(f"Email enviado exitosamente para reporte ID: {nuevo_reporte.id}")
            else:
                current_app.logger.warning(f"No se pudo enviar email para reporte ID: {nuevo_reporte.id}")
                
        except Exception as email_error:
            # No fallar la creación del reporte si el email falla
            current_app.logger.error(f"Error al enviar email para reporte ID {nuevo_reporte.id}: {str(email_error)}")
        
        # Preparar respuesta
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

@reportes_bp.route('/reportes', methods=['GET'])
def obtener_reportes():
    try:
        # Obtener parámetros de paginación
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Limitar per_page para evitar sobrecarga
        per_page = min(per_page, 100)
        
        # Obtener reportes paginados
        reportes_paginados = Reporte.query.order_by(Reporte.fecha_creacion.desc()).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        reportes_lista = [reporte.to_dict() for reporte in reportes_paginados.items]
        
        return jsonify({
            'reportes': reportes_lista,
            'total': reportes_paginados.total,
            'pages': reportes_paginados.pages,
            'current_page': page,
            'per_page': per_page
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error al obtener reportes: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@reportes_bp.route('/reportes/<int:reporte_id>', methods=['GET'])
def obtener_reporte(reporte_id):
    try:
        reporte = Reporte.query.get_or_404(reporte_id)
        return jsonify({'reporte': reporte.to_dict()}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error al obtener reporte {reporte_id}: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@reportes_bp.route('/reportes/<int:reporte_id>', methods=['DELETE'])
def eliminar_reporte(reporte_id):
    try:
        reporte = Reporte.query.get_or_404(reporte_id)
        
        # Eliminar archivos de fotos del sistema de archivos
        for foto in reporte.fotos:
            ruta_completa = os.path.join(current_app.static_folder, foto.ruta_archivo.lstrip('/'))
            if os.path.exists(ruta_completa):
                os.remove(ruta_completa)
        
        # Eliminar reporte (las fotos se eliminan automáticamente por cascade)
        db.session.delete(reporte)
        db.session.commit()
        
        return jsonify({'mensaje': 'Reporte eliminado exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al eliminar reporte {reporte_id}: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500



    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al crear reporte: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500
