from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from datetime import datetime
import hashlib

admin_bp = Blueprint('admin', __name__)

# Contraseña del administrador (en producción debería estar en variables de entorno)
ADMIN_PASSWORD = "cerrolargo2025"

def hash_password(password):
    """Hash de la contraseña para mayor seguridad"""
    return hashlib.sha256(password.encode()).hexdigest()

@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Autenticación del administrador"""
    try:
        data = request.get_json()
        password = data.get('password', '')
        
        if password == ADMIN_PASSWORD:
            session['admin_authenticated'] = True
            return jsonify({
                'success': True,
                'message': 'Autenticación exitosa'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Contraseña incorrecta'
            }), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error en la autenticación: {str(e)}'
        }), 500

@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    """Cerrar sesión del administrador"""
    session.pop('admin_authenticated', None)
    return jsonify({
        'success': True,
        'message': 'Sesión cerrada'
    }), 200

@admin_bp.route('/check-auth', methods=['GET'])
def check_auth():
    """Verificar si el administrador está autenticado"""
    is_authenticated = session.get('admin_authenticated', False)
    return jsonify({
        'authenticated': is_authenticated
    }), 200

def require_admin_auth(f):
    """Decorador para requerir autenticación de administrador"""
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated', False):
            return jsonify({
                'success': False,
                'message': 'Acceso no autorizado'
            }), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/zones/states', methods=['GET'])
def get_zone_states():
    """Obtener todos los estados de las zonas"""
    try:
        states = ZoneState.get_all_states()
        return jsonify({
            'success': True,
            'states': states
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener estados: {str(e)}'
        }), 500

@admin_bp.route('/zones/update-state', methods=['POST'])
@require_admin_auth
def update_zone_state():
    """Actualizar el estado de una zona"""
    try:
        data = request.get_json()
        zone_name = data.get('zone_name')
        state = data.get('state')
        
        if not zone_name or not state:
            return jsonify({
                'success': False,
                'message': 'Nombre de zona y estado son requeridos'
            }), 400
        
        if state not in ['green', 'yellow', 'red']:
            return jsonify({
                'success': False,
                'message': 'Estado debe ser green, yellow o red'
            }), 400
        
        updated_zone = ZoneState.update_zone_state(zone_name, state, 'admin')
        
        return jsonify({
            'success': True,
            'message': 'Estado actualizado correctamente',
            'zone': updated_zone
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al actualizar estado: {str(e)}'
        }), 500

@admin_bp.route('/zones/bulk-update', methods=['POST'])
@require_admin_auth
def bulk_update_zones():
    """Actualizar múltiples zonas a la vez"""
    try:
        data = request.get_json()
        updates = data.get('updates', [])
        
        if not updates:
            return jsonify({
                'success': False,
                'message': 'No se proporcionaron actualizaciones'
            }), 400
        
        updated_zones = []
        for update in updates:
            zone_name = update.get('zone_name')
            state = update.get('state')
            
            if zone_name and state and state in ['green', 'yellow', 'red']:
                updated_zone = ZoneState.update_zone_state(zone_name, state, 'admin')
                updated_zones.append(updated_zone)
        
        return jsonify({
            'success': True,
            'message': f'Se actualizaron {len(updated_zones)} zonas',
            'updated_zones': updated_zones
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error en actualización masiva: {str(e)}'
        }), 500

@admin_bp.route('/report/generate', methods=['GET'])
@require_admin_auth
def generate_report():
    """Generar reporte de estados de zonas"""
    try:
        states = ZoneState.get_all_states()
        
        # Contar estados
        state_counts = {'green': 0, 'yellow': 0, 'red': 0}
        for zone_data in states.values():
            state = zone_data.get('state', 'green')
            state_counts[state] = state_counts.get(state, 0) + 1
        
        report_data = {
            'generated_at': datetime.utcnow().isoformat(),
            'total_zones': len(states),
            'state_summary': state_counts,
            'zones': states
        }
        
        return jsonify({
            'success': True,
            'report': report_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al generar reporte: {str(e)}'
        }), 500

