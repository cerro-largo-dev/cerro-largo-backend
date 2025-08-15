from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from datetime import datetime
from functools import wraps
import os

admin_bp = Blueprint('admin', __name__)

# En prod, usar env var
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "cerrolargo2025")
SESSION_FLAG = "admin_authenticated"  # ← coherente con tu cookie histórica

def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get(SESSION_FLAG, False):
            return jsonify({"success": False, "message": "Acceso no autorizado"}), 401
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Contraseña incorrecta"}), 401
    session[SESSION_FLAG] = True
    return jsonify({"success": True, "message": "Autenticación exitosa"}), 200

@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    session.pop(SESSION_FLAG, None)
    return jsonify({"success": True, "message": "Sesión cerrada"}), 200

@admin_bp.route('/check-auth', methods=['GET'])
def check_auth():
    return jsonify({"success": True, "authenticated": session.get(SESSION_FLAG, False)}), 200

@admin_bp.route('/zones/states', methods=['GET'])
def get_zone_states():
    """Público (si lo quieres protegido, añade @require_admin_auth)."""
    try:
        states = ZoneState.get_all_states()
        return jsonify({"success": True, "states": states}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error al obtener estados: {str(e)}"}), 500

@admin_bp.route('/zones/update-state', methods=['POST'])
@require_admin_auth
def update_zone_state():
    try:
        data = request.get_json(silent=True) or {}
        zone_name = data.get('zone_name')
        state = data.get('state')
        if not zone_name or not state:
            return jsonify({"success": False, "message": "Nombre de zona y estado son requeridos"}), 400
        if state not in ['green', 'yellow', 'red']:
            return jsonify({"success": False, "message": "Estado debe ser green, yellow o red"}), 400

        updated_zone = ZoneState.update_zone_state(zone_name, state, 'admin')
        if updated_zone:
            return jsonify({
                "success": True,
                "message": "Estado actualizado correctamente",
                "zone": updated_zone.to_dict()
            }), 200
        else:
            return jsonify({"success": False, "message": "Error al actualizar o crear la zona"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Error al actualizar estado: {str(e)}"}), 500

@admin_bp.route('/zones/bulk-update', methods=['POST'])
@require_admin_auth
def bulk_update_zones():
    try:
        data = request.get_json(silent=True) or {}
        updates = data.get('updates', [])
        if not updates:
            return jsonify({"success": False, "message": "No se proporcionaron actualizaciones"}), 400

        updated = []
        for upd in updates:
            zn = upd.get('zone_name')
            st = upd.get('state')
            if zn and st in ['green', 'yellow', 'red']:
                z = ZoneState.update_zone_state(zn, st, 'admin')
                if z:
                    updated.append(z.to_dict())

        return jsonify({"success": True, "message": f"Se actualizaron {len(updated)} zonas", "updated_zones": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error en actualización masiva: {str(e)}"}), 500
