from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from werkzeug.security import check_password_hash
import hashlib

admin_bp = Blueprint('admin', __name__)

# Credenciales de administrador simples (en producción usar base de datos)
ADMIN_CREDENTIALS = {
    'admin': hashlib.sha256('admin123'.encode()).hexdigest()
}

def require_admin_auth(f):
    """Decorador para requerir autenticación de administrador"""
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated', False):
            return jsonify({
                'success': False,
                'message': 'Acceso no autorizado. Debe autenticarse como administrador.'
            }), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Autenticación de administrador"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'message': 'Usuario y contraseña son requeridos'
            }), 400
        
        # Verificar credenciales
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if username in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[username] == password_hash:
            session['admin_authenticated'] = True
            session['admin_username'] = username
            return jsonify({
                'success': True,
                'message': 'Autenticación exitosa'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Credenciales incorrectas'
            }), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error en autenticación: {str(e)}'
        }), 500

@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    """Cerrar sesión de administrador"""
    session.pop('admin_authenticated', None)
    session.pop('admin_username', None)
    return jsonify({
        'success': True,
        'message': 'Sesión cerrada exitosamente'
    }), 200

@admin_bp.route('/zones', methods=['GET'])
@require_admin_auth
def get_zones_admin():
    """Obtener todas las zonas (solo administrador)"""
    try:
        zones = ZoneState.query.all()
        zones_data = [zone.to_dict() for zone in zones]
        
        return jsonify({
            'success': True,
            'zones': zones_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener zonas: {str(e)}'
        }), 500

@admin_bp.route('/zones/<zone_name>/state', methods=['PUT'])
@require_admin_auth
def update_zone_state(zone_name):
    """Actualizar el estado de una zona (solo administrador)"""
    try:
        data = request.get_json()
        new_state = data.get('state')
        notes = data.get('notes', '')
        
        if not new_state or new_state not in ['green', 'yellow', 'red']:
            return jsonify({
                'success': False,
                'message': 'Estado inválido. Debe ser green, yellow o red'
            }), 400
        
        admin_username = session.get('admin_username', 'admin')
        updated_zone = ZoneState.update_zone_state(zone_name, new_state, admin_username, notes)
        
        return jsonify({
            'success': True,
            'message': f'Estado de {zone_name} actualizado a {new_state}',
            'zone': updated_zone.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al actualizar zona: {str(e)}'
        }), 500

@admin_bp.route('/zones', methods=['POST'])
@require_admin_auth
def create_zone():
    """Crear una nueva zona (solo administrador)"""
    try:
        data = request.get_json()
        zone_name = data.get('zone_name')
        state = data.get('state', 'green')
        notes = data.get('notes', '')
        
        if not zone_name:
            return jsonify({
                'success': False,
                'message': 'Nombre de zona es requerido'
            }), 400
        
        # Verificar si la zona ya existe
        existing_zone = ZoneState.query.filter_by(zone_name=zone_name).first()
        if existing_zone:
            return jsonify({
                'success': False,
                'message': 'La zona ya existe'
            }), 409
        
        admin_username = session.get('admin_username', 'admin')
        new_zone = ZoneState.update_zone_state(zone_name, state, admin_username, notes)
        
        return jsonify({
            'success': True,
            'message': f'Zona {zone_name} creada exitosamente',
            'zone': new_zone.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al crear zona: {str(e)}'
        }), 500

@admin_bp.route('/status', methods=['GET'])
def admin_status():
    """Verificar estado de autenticación"""
    return jsonify({
        'authenticated': session.get('admin_authenticated', False),
        'username': session.get('admin_username')
    }), 200
