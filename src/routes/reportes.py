# src/routes/reportes.py — actualizado (recompresión a WEBP + validaciones)
import os
import io
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

from src.models.reporte import db, Reporte, FotoReporte
from src.utils.email_service import EmailService

reportes_bp = Blueprint('reportes', __name__)

# ---- Configuración de subida ----
# Restringimos a formatos estándar y recomprimimos a WEBP (sin EXIF)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
# 8 MB para alinear con app.config['MAX_CONTENT_LENGTH'] en main.py
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB

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

# -----------------------------------------------------------------------------
# Crear reporte (con fotos opcionales)
# -----------------------------------------------------------------------------
@reportes_bp.route('/reportes', methods=['POST'])
def crear_reporte():
    try:
        descripcion = request.form.get('descripcion')
        nombre_lugar = request.form.get('nombre_lugar', '')
        latitud = request.form.get('latitud')
        longitud = request.form.get('longitud')

        if not descripcion:
            return jsonify({'error': 'La descripción es obligatoria'}), 400

        # Coordenadas a float
        try:
            latitud = float(latitud) if latitud else None
            longitud = float(longitud) if longitud else None
        except (ValueError, TypeError):
            latitud = None
            longitud = None

        # Crea el reporte (visible por defecto = False)
        nuevo_reporte = Reporte(
            descripcion=descripcion,
            nombre_lugar=nombre_lugar if nombre_lugar else None,
            latitud=latitud,
            longitud=longitud,
            visible=False
        )
        db.session.add(nuevo_reporte)
        db.session.commit()  # tener id y fecha_creacion

        # Manejo de fotos
        fotos_guardadas = []
        fotos_rechazadas = []

        if 'fotos' in request.files:
            fotos = request.files.getlist('fotos')
            upload_dir = get_upload_dir()

            for foto in fotos:
                if not (foto and foto.filename):
                    continue

                # 1) Validar extensión declarada
                if not allowed_file(foto.filename):
                    fotos_rechazadas.append({
                        'nombre': foto.filename,
                        'razon': f'Tipo de archivo no permitido. Permitidos: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
                    })
                    continue

                # 2) Leer contenido y validar tamaño real
                try:
                    raw = foto.read()
                except Exception as read_err:
                    fotos_rechazadas.append({'nombre': foto.filename, 'razon': f'No se pudo leer el archivo: {read_err}'})
                    continue

                file_size = len(raw)
                # Chequeo contra límite local y el global de Flask
                max_len = min(MAX_FILE_SIZE, int(current_app.config.get('MAX_CONTENT_LENGTH', MAX_FILE_SIZE)))
                if file_size > max_len:
                    fotos_rechazadas.append({
                        'nombre': foto.filename,
                        'razon': f'Archivo demasiado grande ({file_size/(1024*1024):.1f}MB). '
                                 f'Máximo permitido: {max_len/(1024*1024):.1f}MB'
                    })
                    continue

                # 3) Validar que realmente sea una imagen y recomprimir a WEBP (quita EXIF)
                try:
                    img = Image.open(io.BytesIO(raw))
                    # Si quisieras verificar antes: img.verify(); pero requiere reabrir. Vamos directo a convertir.
                    img = img.convert("RGB")  # normalizamos y removemos alfa si la hubiera
                except UnidentifiedImageError:
                    fotos_rechazadas.append({'nombre': foto.filename, 'razon': 'Archivo no es una imagen válida'})
                    continue
                except Exception as id_err:
                    fotos_rechazadas.append({'nombre': foto.filename, 'razon': f'No se pudo procesar la imagen: {id_err}'})
                    continue

                # 4) Salida WEBP
                out = io.BytesIO()
                try:
                    img.save(out, format="WEBP", quality=80, method=6)  # sin metadatos/EXIF
                except Exception as enc_err:
                    fotos_rechazadas.append({'nombre': foto.filename, 'razon': f'Fallo al recomprimir: {enc_err}'})
                    continue
                out.seek(0)

                # 5) Guardar a disco con nombre único y extensión .webp
                nombre_unico = f"{uuid.uuid4().hex}.webp"
                nombre_seguro = secure_filename(nombre_unico)
                ruta_archivo_abs = os.path.join(upload_dir, nombre_seguro)

                try:
                    with open(ruta_archivo_abs, "wb") as f:
                        f.write(out.read())
                except Exception as write_err:
                    fotos_rechazadas.append({'nombre': foto.filename, 'razon': f'Error al guardar: {write_err}'})
                    continue

                # 6) Registrar en DB (ruta pública relativa a /static)
                foto_reporte = FotoReporte(
                    reporte_id=nuevo_reporte.id,
                    # Guardamos el nombre original como referencia; el archivo físico es .webp
                    nombre_archivo=foto.filename,
                    ruta_archivo=f"/uploads/reportes/{nombre_seguro}"
                )
                db.session.add(foto_reporte)
                fotos_guardadas.append(foto_reporte.to_dict())

        db.session.commit()

        # Enviar email (no rompe si falla)
        try:
            email_service = EmailService()
            reporte_email_data = {
                'descripcion': descripcion,
                'nombre_lugar': nombre_lugar,
                'latitud': latitud,
                'longitud': longitud,
                'fecha_creacion': nuevo_reporte.fecha_creacion.isoformat() if nuevo_reporte.fecha_creacion else None
            }

            rutas_fotos = []
            if fotos_guardadas:
                upload_dir = get_upload_dir()
                for foto in fotos_guardadas:
                    # FotoReporte.to_dict() debe incluir ruta_archivo (ej: /uploads/reportes/<uuid>.webp)
                    nombre_archivo = foto.get('ruta_archivo', '').split('/')[-1]
                    if not nombre_archivo:
                        continue
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

        # Respuesta
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

# -----------------------------------------------------------------------------
# Listar reportes paginados
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Obtener un reporte
# -----------------------------------------------------------------------------
@reportes_bp.route('/reportes/<int:reporte_id>', methods=['GET'])
def obtener_reporte(reporte_id):
    try:
        reporte = Reporte.query.get_or_404(reporte_id)
        return jsonify({'reporte': reporte.to_dict()}), 200
    except Exception as e:
        current_app.logger.error(f"Error al obtener reporte {reporte_id}: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500

# -----------------------------------------------------------------------------
# Eliminar un reporte (y sus archivos físicos)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# NUEVO: Marcar visible / oculto
# -----------------------------------------------------------------------------
@reportes_bp.route('/reportes/<int:reporte_id>/visible', methods=['PATCH'])
def set_visible(reporte_id):
    try:
        body = request.get_json(force=True, silent=True) or {}
        v = bool(body.get('visible'))
        r = Reporte.query.get_or_404(reporte_id)
        r.visible = v
        db.session.commit()
        return jsonify({'ok': True, 'reporte': r.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error set_visible {reporte_id}: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

# -----------------------------------------------------------------------------
# NUEVO: Lista de reportes visibles (para pintar en mapa)
# -----------------------------------------------------------------------------
@reportes_bp.route('/reportes/visibles', methods=['GET'])
def list_visibles():
    try:
        q = (Reporte.query
             .filter(Reporte.visible.is_(True),
                     Reporte.latitud.isnot(None),
                     Reporte.longitud.isnot(None))
             .order_by(Reporte.fecha_creacion.desc())
             .limit(200))
        data = [r.to_dict() for r in q.all()]
        # Para el mapa alcanzan los campos básicos, pero devolvemos to_dict completo
        return jsonify({'ok': True, 'reportes': data}), 200
    except Exception as e:
        current_app.logger.error(f"Error list_visibles: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
