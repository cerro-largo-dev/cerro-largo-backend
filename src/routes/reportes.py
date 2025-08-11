from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from src.models.reportes import db, Reporte, FotoReporte
from src.utils.email_service import EmailService
import os
import uuid

# Blueprint en /api
reportes_bp = Blueprint('reportes', __name__, url_prefix='/api')

# ---- Config subida de archivos ----
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_upload_dir() -> str:
    """Crea (si no existe) y retorna el directorio de uploads para reportes."""
    base = current_app.static_folder
    upload_dir = os.path.join(base, 'uploads', 'reportes')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir

# ---- Endpoints ----

@reportes_bp.route('/reportes', methods=['POST'])
def crear_reporte():
    try:
        # Datos básicos
        descripcion = request.form.get('descripcion')
        nombre_lugar = request.form.get('nombre_lugar', '').strip() or None
        latitud = request.form.get('latitud')
        longitud = request.form.get('longitud')

        if not descripcion:
            return jsonify({'error': 'La descripción es obligatoria'}), 400

        # Coordenadas (opcionales)
        try:
            latitud = float(latitud) if latitud not in (None, '',) else None
            longitud = float(longitud) if longitud not in (None, '',) else None
            if latitud is not None and not (-90 <= latitud <= 90):
                return jsonify({'error': 'Latitud fuera de rango'}), 400
            if longitud is not None and not (-180 <= longitud <= 180):
                return jsonify({'error': 'Longitud fuera de rango'}), 400
        except (ValueError, TypeError):
            latitud, longitud = None, None

        # Crear reporte
        nuevo_reporte = Reporte(
            descripcion=descripcion,
            nombre_lugar=nombre_lugar,
            latitud=latitud,
            longitud=longitud
        )
        db.session.add(nuevo_reporte)
        db.session.flush()  # obtener ID

        # Subida de fotos (opcional)
        fotos_guardadas = []
        if 'fotos' in request.files:
            upload_dir = ensure_upload_dir()
            for foto in request.files.getlist('fotos'):
                if not (foto and foto.filename):
                    continue
                if not allowed_file(foto.filename):
                    continue

                # Control de tamaño
                pos = foto.tell()
                contenido = foto.read()
                if len(contenido) > MAX_FILE_SIZE:
                    return jsonify({'error': 'El archivo es demasiado grande (máx 16MB)'}), 400
                foto.seek(pos)  # reset

                # Nombre único
                ext = foto.filename.rsplit('.', 1)[1].lower()
                nombre_unico = f"{uuid.uuid4().hex}.{ext}"
                nombre_seguro = secure_filename(nombre_unico)

                # Guardar archivo
                ruta_fs = os.path.join(upload_dir, nombre_seguro)
                foto.save(ruta_fs)

                # Registrar en BD
                registro = FotoReporte(
                    reporte_id=nuevo_reporte.id,
                    nombre_archivo=foto.filename,
                    ruta_archivo=f"/uploads/reportes/{nombre_seguro}"
                )
                db.session.add(registro)
                fotos_guardadas.append(registro.to_dict())

        # Confirmar transacción
        db.session.commit()

        # Enviar email (no bloqueante)
        try:
            email_service = EmailService()
            data_email = {
                'descripcion': descripcion,
                'nombre_lugar': nombre_lugar,
                'latitud': latitud,
                'longitud': longitud,
                'fecha_creacion': nuevo_reporte.fecha_creacion.isoformat()
            }

            rutas_fotos = []
            if fotos_guardadas:
                upload_dir = ensure_upload_dir()
                for f in fotos_guardadas:
                    nombre_archivo = f['ruta_archivo'].split('/')[-1]
                    ruta_completa = os.path.join(upload_dir, nombre_archivo)
                    if os.path.exists(ruta_completa):
                        rutas_fotos.append(ruta_completa)

            email_service.enviar_reporte_ciudadano(data_email, rutas_fotos)
        except Exception as e_email:
            current_app.logger.error(f"[Email] Error reporte {nuevo_reporte.id}: {e_email}")

        # Respuesta
        out = nuevo_reporte.to_dict()
        out['fotos'] = fotos_guardadas
        return jsonify({'mensaje': 'Reporte creado exitosamente', 'reporte': out}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[POST /api/reportes] {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500


@reportes_bp.route('/reportes', methods=['GET'])
def obtener_reportes():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)

        pag = Reporte.query.order_by(Reporte.fecha_creacion.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        items = [r.to_dict() for r in pag.items]
        return jsonify({
            'reportes': items,
            'total': pag.total,
            'pages': pag.pages,
            'current_page': page,
            'per_page': per_page
        }), 200

    except Exception as e:
        current_app.logger.error(f"[GET /api/reportes] {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500


@reportes_bp.route('/reportes/<int:reporte_id>', methods=['GET'])
def obtener_reporte(reporte_id: int):
    try:
        r = Reporte.query.get_or_404(reporte_id)
        return jsonify({'reporte': r.to_dict()}), 200
    except Exception as e:
        current_app.logger.error(f"[GET /api/reportes/{reporte_id}] {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500


@reportes_bp.route('/reportes/<int:reporte_id>', methods=['DELETE'])
def eliminar_reporte(reporte_id: int):
    try:
        r = Reporte.query.get_or_404(reporte_id)

        # Borrar archivos físicos
        upload_base = current_app.static_folder
        for f in r.fotos:
            ruta = os.path.join(upload_base, f.ruta_archivo.lstrip('/'))
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except Exception as e_fs:
                current_app.logger.warning(f"[FS] No se pudo eliminar {ruta}: {e_fs}")

        db.session.delete(r)
        db.session.commit()
        return jsonify({'mensaje': 'Reporte eliminado exitosamente'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[DELETE /api/reportes/{reporte_id}] {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
