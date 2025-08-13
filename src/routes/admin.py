from flask import Blueprint, request, jsonify, session
from functools import wraps
from models.zone_state import ZoneState, db
from models.user import User
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

# --------- Helpers ---------
def require_role(required_role):
    """Requiere sesión y rol específico."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                return jsonify(success=False, message='No autenticado'), 401

            role = session.get('role')
            if required_role == 'admin' and role != 'admin':
                return jsonify(success=False, message='Se requiere rol admin'), 403
            if required_role == 'alcalde' and role != 'alcalde':
                return jsonify(success=False, message='Se requiere rol alcalde'), 403

            return f(*args, **kwargs)
        return decorated
    return decorator

def require_municipality_access(f):
    """Admin accede a todo; alcalde solo a su municipio (según zone_name)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify(success=False, message='No autenticado'), 401

        role = session.get('role')
        if role == 'admin':
            return f(*args, **kwargs)

        if role == 'alcalde':
            data = request.get_json(silent=True) or {}
            zone_name = data.get('zone_name')
            user_municipality = session.get('municipality')
            if zone_name and zone_name != user_municipality:
                return jsonify(success=False,
                               message=f'Acceso denegado: Solo puede modificar {user_municipality}'), 403

        return f(*args, **kwargs)
    return decorated

# --------- Auth ---------
@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Autenticación."""
    try:
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '')

        if not username or not password:
            return jsonify(success=False, message='Faltan credenciales'), 400

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            # (Opcional) limitar roles válidos
            if user.role not in ('admin', 'alcalde'):
                return jsonify(success=False, message='Rol no autorizado'), 403

            session.permanent = True  # si configuraste PERMANENT_SESSION_LIFETIME
            session['logged_in'] = True
            session['user_id'] = user.id
            session['role'] = user.role
            session['municipality'] = user.municipality

            return jsonify(success=True,
                           message='Autenticación exitosa',
                           role=user.role,
                           municipality=user.municipality), 200

        return jsonify(success=False, message='Usuario o contraseña incorrectos'), 401

    except Exception as e:
        return jsonify(success=False, message=f'Error en la autenticación: {str(e)}'), 500

@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify(success=True, message='Sesión cerrada'), 200

@admin_bp.route('/check-auth', methods=['GET'])
def check_auth():
    return jsonify(
        authenticated=bool(session.get('logged_in')),
        role=session.get('role'),
        municipality=session.get('municipality')
    ), 200

# --------- Zonas ---------
@admin_bp.route('/zones/states', methods=['GET'])
@require_role('admin')
def get_zone_states():
    try:
        states = ZoneState.get_all_states()  # debe retornar dict serializable
        return jsonify(success=True, states=states), 200
    except Exception as e:
        return jsonify(success=False, message=f'Error al obtener estados: {str(e)}'), 500

@admin_bp.route('/zones/update-state', methods=['POST'])
@require_municipality_access
def update_zone_state():
    try:
        data = request.get_json(silent=True) or {}
        zone_name = data.get('zone_name')
        state = data.get('state')

        if not zone_name or not state:
            return jsonify(success=False, message='zone_name y state son requeridos'), 400

        if state not in {'green', 'yellow', 'red'}:
            return jsonify(success=False, message='state debe ser green, yellow o red'), 400

        updated_by = f"{session.get('role')}_{session.get('user_id')}"
        updated_zone = ZoneState.update_zone_state(zone_name, state, updated_by)

        if not updated_zone:
            return jsonify(success=False, message='Error al actualizar o crear la zona'), 500

        return jsonify(success=True,
                       message='Estado actualizado correctamente',
                       zone=updated_zone.to_dict()), 200
    except Exception as e:
        return jsonify(success=False, message=f'Error al actualizar estado: {str(e)}'), 500

@admin_bp.route('/zones/bulk-update', methods=['POST'])
@require_role('admin')
def bulk_update_zones():
    try:
        data = request.get_json(silent=True) or {}
        updates = data.get('updates') or []
        if not updates:
            return jsonify(success=False, message='No se proporcionaron actualizaciones'), 400

        updated = []
        updated_by = f"admin_{session.get('user_id')}"
        for u in updates:
            zone_name = u.get('zone_name')
            state = u.get('state')
            if not zone_name or state not in {'green', 'yellow', 'red'}:
                continue
            z = ZoneState.update_zone_state(zone_name, state, updated_by)
            if z:
                updated.append(z.to_dict())

        return jsonify(success=True,
                       message=f'Se actualizaron {len(updated)} zonas',
                       updated_zones=updated), 200
    except Exception as e:
        return jsonify(success=False, message=f'Error en actualización masiva: {str(e)}'), 500

# --------- Usuarios ---------
@admin_bp.route('/create-user', methods=['POST'])
@require_role('admin')
def create_user():
    try:
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '')
        role = (data.get('role') or '').strip()
        municipality = (data.get('municipality') or None)

        if not username or not password or role not in {'admin', 'alcalde'}:
            return jsonify(success=False,
                           message='username, password y role (admin|alcalde) son requeridos'), 400

        if role == 'alcalde' and not municipality:
            return jsonify(success=False, message='municipality es requerido para alcalde'), 400

        if User.query.filter_by(username=username).first():
            return jsonify(success=False, message='El usuario ya existe'), 400

        hashed = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username,
                        password_hash=hashed,
                        role=role,
                        municipality=municipality if role == 'alcalde' else None)
        db.session.add(new_user)
        db.session.commit()

        return jsonify(success=True, message='Usuario creado exitosamente', user=new_user.to_dict()), 201
    except Exception as e:
        return jsonify(success=False, message=f'Error al crear usuario: {str(e)}'), 500
