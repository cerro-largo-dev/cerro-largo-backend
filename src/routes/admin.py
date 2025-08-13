from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from src.models.user import User
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Autenticación del administrador"""
    try:
        data = request.get_json()
        username = data.get('username', '')
        password = data.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session['logged_in'] = True
            session['user_id'] = user.id
            session['role'] = user.role
            session['municipality'] = user.municipality
            return jsonify({
                'success': True,
                'message': 'Autenticación exitosa',
                'role': user.role,
                'municipality': user.municipality
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Usuario o contraseña incorrectos'
            }), 401

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error en la autenticación: {str(e)}'
        }), 500

@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    """Cerrar sesión del administrador"""
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('role', None)
    session.pop('municipality', None)
    return jsonify({
        'success': True,
        'message': 'Sesión cerrada'
    }), 200

@admin_bp.route('/check-auth', methods=['GET'])
def check_auth():
    """Verificar si el administrador está autenticado"""
    is_authenticated = session.get('logged_in', False)
    role = session.get('role', None)
    municipality = session.get('municipality', None)
    return jsonify({
        'authenticated': is_authenticated,
        'role': role,
        'municipality': municipality
    }), 200

def require_role(required_role):
    """Decorador para requerir autenticación y rol específico"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in', False):
                return jsonify({
                    'success': False,
                    'message': 'Acceso no autorizado: No autenticado'
                }), 401

            user_role = session.get('role')
            user_municipality = session.get('municipality')

            if required_role == 'admin':
                if user_role != 'admin':
                    return jsonify({
                        'success': False,
                        'message': 'Acceso no autorizado: Se requiere rol de administrador'
                    }), 403
            elif required_role == 'alcalde':
                if user_role != 'alcalde':
                    return jsonify({
                        'success': False,
                        'message': 'Acceso no autorizado: Se requiere rol de alcalde'
                    }), 403

            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

def require_municipality_access(f):
    """Decorador para verificar acceso a municipio específico"""
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in', False):
            return jsonify({
                'success': False,
                'message': 'Acceso no autorizado: No autenticado'
            }), 401

        user_role = session.get('role')
        user_municipality = session.get('municipality')
        
        # Si es admin, puede acceder a todo
        if user_role == 'admin':
            return f(*args, **kwargs)
        
        # Si es alcalde, verificar que solo acceda a su municipio
        if user_role == 'alcalde':
            data = request.get_json()
            zone_name = data.get('zone_name') if data else None
            
            if zone_name and zone_name != user_municipality:
                return jsonify({
                    'success': False,
                    'message': f'Acceso denegado: Solo puede modificar {user_municipality}'
                }), 403
        
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/zones/states', methods=['GET'])
@require_role('admin')
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
@require_municipality_access
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
        
        # Obtener el usuario que actualiza
        user_role = session.get('role')
        updated_by = f"{user_role}_{session.get('user_id')}"
        
        updated_zone = ZoneState.update_zone_state(zone_name, state, updated_by)
        if updated_zone:
            return jsonify({
                'success': True,
                'message': 'Estado actualizado correctamente',
                'zone': updated_zone.to_dict()
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Error al actualizar o crear la zona'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al actualizar estado: {str(e)}'
        }), 500

@admin_bp.route('/zones/bulk-update', methods=['POST'])
@require_role('admin')
def bulk_update_zones():
    """Actualizar múltiples zonas a la vez - Solo administradores"""
    try:
        data = request.get_json()
        updates = data.get('updates', [])
        
        if not updates:
            return jsonify({
                'success': False,
                'message': 'No se proporcionaron actualizaciones'
            }), 400
        
        updated_zones = []
        updated_by = f"admin_{session.get('user_id')}"
        
        for update in updates:
            zone_name = update.get('zone_name')
            state = update.get('state')
            
            if zone_name and state and state in ['green', 'yellow', 'red']:
                updated_zone = ZoneState.update_zone_state(zone_name, state, updated_by)
                if updated_zone:
                    updated_zones.append(updated_zone.to_dict())
        
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
@require_role('admin')
def generate_report():
    """Generar reporte de estados de zonas - Solo administradores"""
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

@admin_bp.route('/create-user', methods=['POST'])
@require_role('admin')
def create_user():
    """Crear un nuevo usuario - Solo administradores"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        role = data.get('role')
        municipality = data.get('municipality')
        
        if not username or not password or not role:
            return jsonify({
                'success': False,
                'message': 'Username, password y role son requeridos'
            }), 400
        
        if role not in ['admin', 'alcalde']:
            return jsonify({
                'success': False,
                'message': 'Role debe ser admin o alcalde'
            }), 400
        
        if role == 'alcalde' and not municipality:
            return jsonify({
                'success': False,
                'message': 'Municipality es requerido para role alcalde'
            }), 400
        
        # Verificar si el usuario ya existe
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({
                'success': False,
                'message': 'El usuario ya existe'
            }), 400
        
        # Crear el nuevo usuario
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(
            username=username,
            password_hash=hashed_password,
            role=role,
            municipality=municipality if role == 'alcalde' else None
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Usuario creado exitosamente',
            'user': new_user.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al crear usuario: {str(e)}'
        }), 500
