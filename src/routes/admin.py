from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from datetime import datetime
from functools import wraps
import os
import json
import unicodedata

admin_bp = Blueprint('admin', __name__)

# Config
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "cerrolargo2025")
SESSION_FLAG = "admin_authenticated"  # coherente con cookie histórica
# JSON: {"AREVALO":"passarevalo","MELO":"passmelo"}
ZONE_EDITORS_JSON = os.environ.get("ZONE_EDITORS_JSON", "")

# Utils de canonización (mayúsculas, sin acentos)

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def canon(s: str) -> str:
    if not s:
        return ''
    return _strip_accents(s).upper().strip()

def load_zone_editors():
    mapping = {}
    if ZONE_EDITORS_JSON:
        try:
            env_map = json.loads(ZONE_EDITORS_JSON)
            for k, v in (env_map or {}).items():
                if v:
                    mapping[canon(k)] = str(v)
        except Exception:
            pass
    return mapping

ZONE_EDITORS = load_zone_editors()  # { 'AREVALO': 'passarevalo', ... }

# Decoradores

def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get(SESSION_FLAG, False):
            return jsonify({"success": False, "message": "Acceso no autorizado"}), 401
        return f(*args, **kwargs)
    return decorated

# Rutas

@admin_bp.route('/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    pwd = str(data.get('password') or '')

    # 1) Admin total
    if pwd == ADMIN_PASSWORD:
        session[SESSION_FLAG] = True
        session['role'] = 'admin'
        session['allowed_zones'] = '*'
        return jsonify({"success": True, "message": "Autenticación admin"}), 200

    # 2) Editor por zona (match por contraseña)
    zones = [z for z, passw in ZONE_EDITORS.items() if passw == pwd]
    if zones:
        session[SESSION_FLAG] = True
        session['role'] = 'editor'
        session['allowed_zones'] = zones  # canónicas
        return jsonify({"success": True, "message": "Autenticación editor", "allowed_zones": zones}), 200

    return jsonify({"success": False, "message": "Contraseña incorrecta"}), 401


@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    session.pop(SESSION_FLAG, None)
    session.pop('role', None)
    session.pop('allowed_zones', None)
    return jsonify({"success": True, "message": "Sesión cerrada"}), 200


@admin_bp.route('/check-auth', methods=['GET'])
def check_auth():
    authed = session.get(SESSION_FLAG, False)
    role = session.get('role', 'admin' if authed else None)
    az = session.get('allowed_zones', '*' if role == 'admin' else [])
    return jsonify({"success": True, "authenticated": bool(authed), "role": role, "allowed_zones": az}), 200


@admin_bp.route('/zones/states', methods=['GET'])
def get_zone_states():
    """Público (si prefieres, protégelo añadiendo @require_admin_auth)."""
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
        state = data.get('state')  # 'green'|'yellow'|'red'
        if not zone_name or not state:
            return jsonify({"success": False, "message": "Nombre de zona y estado son requeridos"}), 400
        if state not in ['green', 'yellow', 'red']:
            return jsonify({"success": False, "message": "Estado debe ser green, yellow o red"}), 400

        # Autorización por zona si es editor
        az = session.get('allowed_zones')
        if az != '*' and az is not None:
            if canon(zone_name) not in [canon(z) for z in (az or [])]:
                return jsonify({"success": False, "message": "No autorizado para esta zona"}), 403

        updated_zone = ZoneState.update_zone_state(zone_name, state, session.get('role', 'admin'))
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

        az = session.get('allowed_zones')
        updated = []
        for upd in updates:
            zn = upd.get('zone_name')
            st = upd.get('state')
            if not zn or st not in ['green', 'yellow', 'red']:
                continue
            if az != '*' and az is not None and canon(zn) not in [canon(z) for z in (az or [])]:
                continue  # skip zonas no permitidas
            z = ZoneState.update_zone_state(zn, st, session.get('role', 'editor'))
            if z:
                updated.append(z.to_dict())

        return jsonify({"success": True, "message": f"Se actualizaron {len(updated)} zonas", "updated_zones": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error en actualización masiva: {str(e)}"}), 500
