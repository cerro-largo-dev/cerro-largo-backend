from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from datetime import datetime
from functools import wraps
import os, json, unicodedata

admin_bp = Blueprint('admin', __name__)

# \-\-\- Config \-\-\-
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "cerrolargo2025")
# Formato ENV: '{"AREVALO":"passarevalo", "MELO":"passmelo"}'
ZONE_EDITORS_JSON = os.environ.get("ZONE_EDITORS_JSON", "")

# Fallback por defecto (puedes dejarlo vacío si usarás solo ENV)
DEFAULT_ZONE_EDITORS = {
    "AREVALO": "passarevalo",
}

# \-\-\- Utils \-\-\-
SESSION_FLAG = "admin_authenticated"  # compatibilidad con tu cookie histórica

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def canon(s: str) -> str:
    if not s: return ''
    return _strip_accents(s).upper().strip()

def load_zone_editors():
    mapping = {}
    # 1) ENV JSON
    if ZONE_EDITORS_JSON:
        try:
            env_map = json.loads(ZONE_EDITORS_JSON)
            for k, v in (env_map or {}).items():
                if v:
                    mapping[canon(k)] = str(v)
        except Exception:
            pass
    # 2) Fallback
    if not mapping:
        for k, v in DEFAULT_ZONE_EDITORS.items():
            mapping[canon(k)] = v
    return mapping

ZONE_EDITORS = load_zone_editors()  # { 'AREVALO': 'passarevalo', ... }

# \-\-\- Auth Helpers \-\-\-

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get(SESSION_FLAG, False):
            return jsonify({"success": False, "message": "Acceso no autorizado"}), 401
        return f(*args, **kwargs)
    return decorated


def is_admin() -> bool:
    return session.get("role") == "admin"


def allowed_zones() -> list:
    az = session.get("allowed_zones")
    if az == "*":
        return "*"
    return list(az or [])

# \-\-\- Rutas \-\-\-

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

    # 2) Editor por zona (buscar coincidencias de contraseña)
    zones = [z for z, passw in ZONE_EDITORS.items() if passw == pwd]
    if zones:
        session[SESSION_FLAG] = True
        session['role'] = 'editor'
        session['allowed_zones'] = zones  # nombres canónicos (mayúscula, sin acentos)
        return jsonify({"success": True, "message": "Autenticación editor", "allowed_zones": zones}), 200

    return jsonify({"success": False, "message": "Contraseña incorrecta"}), 401


@admin_bp.route('/logout', methods=['POST'])
@require_auth
def admin_logout():
    session.clear()
    return jsonify({"success": True, "message": "Sesión cerrada"}), 200


@admin_bp.route('/check-auth', methods=['GET'])
def check_auth():
    auth = bool(session.get(SESSION_FLAG, False))
    role = session.get('role', 'admin' if auth else None)
    az = session.get('allowed_zones', '*' if role == 'admin' else [])
    return jsonify({"success": True, "authenticated": auth, "role": role, "allowed_zones": az}), 200


@admin_bp.route('/zones/states', methods=['GET'])
def get_zone_states():
    """Público por compatibilidad. Si prefieres, añade @require_auth."""
    try:
        states = ZoneState.get_all_states()  # { name: { state, ... }, ... }
        return jsonify({"success": True, "states": states}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error al obtener estados: {str(e)}"}), 500


@admin_bp.route('/zones/update-state', methods=['POST'])
@require_auth
def update_zone_state():
    try:
        data = request.get_json(silent=True) or {}
        zone_name = (data.get('zone_name') or '').strip()
        state = (data.get('state') or '').strip().lower()
        if not zone_name or state not in ['green', 'yellow', 'red']:
            return jsonify({"success": False, "message": "Datos inválidos"}), 400

        # Autorización por zona
        az = allowed_zones()
        if az != '*':
            cz = canon(zone_name)
            # Aceptar equivalencias con/ sin acentos
            if cz not in [canon(z) for z in az]:
                return jsonify({"success": False, "message": "No autorizado para esta zona"}), 403

        # Persistencia
        z = ZoneState.update_zone_state(zone_name, state, session.get('role', 'admin'))
        if z:
            return jsonify({"success": True, "message": "Estado actualizado", "zone": z.to_dict()}), 200
        return jsonify({"success": False, "message": "Error al actualizar"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@admin_bp.route('/zones/bulk-update', methods=['POST'])
@require_auth
def bulk_update_zones():
    try:
        data = request.get_json(silent=True) or {}
        updates = data.get('updates') or []
        if not isinstance(updates, list) or not updates:
            return jsonify({"success": False, "message": "No hay updates"}), 400

        az = allowed_zones()
        updated = []
        for u in updates:
            zn = (u.get('zone_name') or '').strip()
            st = (u.get('state') or '').strip().lower()
            if not zn or st not in ['green','yellow','red']:
                continue
            if az != '*' and canon(zn) not in [canon(z) for z in az]:
                continue  # skip zonas no permitidas
            z = ZoneState.update_zone_state(zn, st, session.get('role','editor'))
            if z: updated.append(z.to_dict())
        return jsonify({"success": True, "updated_zones": updated, "count": len(updated)}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500
