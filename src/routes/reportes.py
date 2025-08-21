# src/routes/reportes.py
import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from src.models.reporte import db, Reporte, FotoReporte
from src.utils.email_service import EmailService

reportes_bp = Blueprint('reportes', __name__)

# ---- Configuración de subida ----
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'heif'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_static_root() -> str:
    """Devuelve un static_root válido incluso si static_folder es None."""
    return current_app.static_folder or os.path.join(current_app.root_path, 'static')

def get_upload_dir() -> str:
    """Devuelve el directorio absoluto para /uploads/reportes y lo asegura."""
    static_root = get_static_root()
    upload_dir = os.path.join(static_root, 'uploads', 'reportes')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir

@reportes_bp.route('/reportes', methods=['POST'])
def crear_reporte():
    try:
        # -------- Datos del formulario --------
        descripcion = request.form.get('descripcion')
        nombre_lugar = request.form.get('nombre_lugar', '')
        latitud = request.form.get('latitud')
        longitud = request.form.get('longitud')

        if not descripcion:
            return jsonify({'error': 'La descripción es obligatoria'}), 400

        # Coordenadas a float (si vienen)
        try:
            latitud = float(latitud) if latitud else None
            longitud = float(longitud) if longitud else None
        except (ValueError, TypeError):
            latitud = None
            longitud = None

        # -------- Crear reporte --------
        nuevo_reporte = Reporte(
            descripcion=descripcion,
            nombre_lugar=nombre_lugar if nombre_lugar else None,
            latitud=latitud,
            longitud=longitud
        )
        db.session.add(nuevo_reporte)
        db.session.commit()  # tener id y fecha_creacion

        # -------- Fotos --------
        fotos_guardadas = []
        fotos_rechazadas = []

        if 'fotos' in request.files:
            fotos = request.files.getlist('fotos')
            upload_dir = get_upload_dir()

            for foto in fotos:
                if not (foto and foto.filename):
                    continue

                # Tamaño
                foto.seek(0, os.SEEK_END)
                file_size = foto.tell()
                foto.seek(0)

                if file_size > MAX_FILE_SIZE:
                    fotos_rechazadas.append({
                        'nombre': foto.filename,
                        'razon': f'Archivo demasiado grande ({file_size/(1024*1024):.1f}MB). '
                                 f'Máximo permitido: {MAX_FILE_SIZE/(1024*1024):.1f}MB'
                    })
                    continue

                if not allowed_file(foto.filename):
                    fotos_rechazadas.append({
                        'nombre': foto.filename,
                        'razon': f'Tipo de archivo no permitido. Permitidos: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
                    })
                    continue

                try:
                    # Nombre único y seguro
                    extension = foto.filename.rsplit('.', 1)[1].lower()
                    nombre_unico = f"{uuid.uuid4().hex}.{extension}"
                    nombre_seguro = secure_filename(nombre_unico)

                    # Guardar
                    ruta_archivo_abs = os.path.join(upload_dir, nombre_seguro)
                    foto.save(ruta_archivo_abs)

                    if not os.path.exists(ruta_archivo_abs):
                        fotos_rechazadas.append({
                            'nombre': foto.filename,
                            'razon': 'Error al guardar el archivo en el servidor'
                        })
                        continue

                    # Registro DB (ruta pública relativa a /static)
                    foto_reporte = FotoReporte(
                        reporte_id=nuevo_reporte.id,
                        nombre_archivo=foto.filename,
                        ruta_archivo=f"/uploads/reportes/{nombre_seguro}"
                    )
                    db.session.add(foto_reporte)
                    fotos_guardadas.append(foto_reporte.to_dict())

                except Exception as foto_error:
                    current_app.logger.error(f"Error al procesar foto {foto.filename}: {str(foto_error)}")
                    fotos_rechazadas.append({
                        'nombre': foto.filename,
                        'razon': f'Error al procesar el archivo: {str(foto_error)}'
                    })

        db.session.commit()

        # -------- Email (no rompe si falla) --------
        try:
            email_service = EmailService()
            reporte_email_data = {
                'descripcion': descripcion,
                'nombre_lugar': nombre_lugar,
                'latitud': latitud,
                'longitud': longitud,
                'fecha_creacion': nuevo_reporte.fecha_creacion.isoformat() if nuevo_reporte.fecha_creacion else None
            }

            # Rutas absolutas para adjuntos
            rutas_fotos = []
            if fotos_guardadas:
                upload_dir = get_upload_dir()
                for foto in fotos_guardadas:
                    nombre_archivo = foto['ruta_archivo'].split('/')[-1]
                    ruta_completa = os.path.join(upload_dir, nombre_archivo)
                    if os.path.exists(ruta_completa):
                        rutas_fotos.append(ruta_completa)

            email_ok = email_service.enviar_reporte_ciudadano(reporte_email_data, rutas_fotos)
            if email_ok:
                current_app.logger.info(f"Email enviado exitosamente para reporte ID: {nuevo_reporte.id}")
            else:
                current_app.logger.warning(f"No se pudo enviar email para reporte ID: {nuevo_reporte.id}")

        except Exception as email_error:
            current_app.logger.error(f"Error al enviar email para reporte ID {nuevo_reporte.id}: {str(email_error)}")

        # -------- Respuesta --------
        reporte_dict = nuevo_reporte.to_dict()
        reporte_dict['fotos'] = fotos_guardadas

        resp = {
            'mensaje': 'Reporte creado exitosamente',
            'reporte': reporte_dict
        }
        if fotos_rechazadas:
            resp['fotos_rechazadas'] = fotos_rechazadas
            resp['mensaje'] += f' (Se rechazaron {len(fotos_rechazadas)} fotos)'

        return jsonify(resp), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al crear reporte: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500


@reportes_bp.route('/reportes', methods=['GET'])
def obtener_reportes():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)

        reportes_paginados = Reporte.query.order_by(Reporte.fecha_creacion.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        reportes_lista = [r.to_dict() for r in reportes_paginados.items]

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

        # borrar archivos físicos
        static_root = get_static_root()
        for foto in reporte.fotos:
            ruta_completa = os.path.join(static_root, foto.ruta_archivo.lstrip('/'))
            if os.path.exists(ruta_completa):
                try:
                    os.remove(ruta_completa)
                except Exception as fs_err:
                    current_app.logger.warning(f"No se pudo borrar archivo {ruta_completa}: {fs_err}")

        db.session.delete(reporte)
        db.session.commit()
        return jsonify({'mensaje': 'Reporte eliminado exitosamente'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al eliminar reporte {reporte_id}: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500
