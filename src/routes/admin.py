from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from functools import wraps
import os
import json
import unicodedata
import pathlib

admin_bp = Blueprint('admin', __name__)

# ---------------- Config ----------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable is required for security")

SESSION_FLAG = "admin_authenticated"  # coherente con tu cookie histórica

# JSON de editores por zona: {"AREVALO":"passarevalo","MELO":"passmelo"}
ZONE_EDITORS_JSON = os.environ.get("ZONE_EDITORS_JSON", "")

# Banner (persistencia simple en archivo)
BANNER_STORE_PATH = os.environ.get("BANNER_STORE_PATH", "/tmp/banner.json")
_DEFAULT_BANNER = {
    "enabled": False,
    "text": "",
    "variant": "info",     # info | warn | alert | success
    "link_text": "",
    "link_href": "",
    "id": ""
}

# ---------------- Utils ----------------
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

# ---------------- Banner helpers ----------------
def _load_banner_cfg():
    try:
        p = pathlib.Path(BANNER_STORE_PATH)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8') or '{}')
            cfg = { **_DEFAULT_BANNER, **(data or {}) }
            cfg["enabled"]   = bool(cfg.get("enabled", False))
            cfg["text"]      = str(cfg.get("text", ""))
            cfg["variant"]   = str(cfg.get("variant", "info")).lower()
            cfg["link_text"] = str(cfg.get("link_text", ""))
            cfg["link_href"] = str(cfg.get("link_href", ""))
            cfg["id"]        = str(cfg.get("id", ""))
            if not cfg["text"].strip():
                cfg["enabled"] = False
            return cfg
    except Exception:
        pass
    return dict(_DEFAULT_BANNER)

def _save_banner_cfg(cfg: dict):
    clean = { **_DEFAULT_BANNER, **(cfg or {}) }
    if not str(clean.get("text", "")).strip():
        clean["enabled"] = False
    p = pathlib.Path(BANNER_STORE_PATH)
    p.write_text(json.dumps(clean, ensure_ascii=False), encoding='utf-8')
    return clean

# ---------------- Decoradores ----------------
def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get(SESSION_FLAG, False):
            return jsonify({"success": False, "message": "Acceso no autorizado"}), 401
        return f(*args, **kwargs)
    return decorated

# ---------------- Auth ----------------
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

    # 2) Editor por zona (coincidencia por contraseña)
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

# ---------------- Zonas ----------------
@admin_bp.route('/zones/states', methods=['GET'])
def get_zone_states():
    """Público (si querés, podés protegerlo agregando @require_admin_auth)."""
    try:
        states = ZoneState.get_all_states()  # { name: { state, ... }, ... }
        return jsonify({"success": True, "states": states}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error al obtener estados: {str(e)}"}), 500

@admin_bp.route('/zones/update-state', methods=['POST'])
@require_admin_auth
def update_zone_state():
    try:
        data = request.get_json(silent=True) or {}
        zone_name = data.get('zone_name')
        state = (data.get('state') or '').strip().lower()
        if not zone_name or state not in ['green', 'yellow', 'red']:
            return jsonify({"success": False, "message": "Datos inválidos"}), 400

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
        if not isinstance(updates, list) or not updates:
            return jsonify({"success": False, "message": "No se proporcionaron actualizaciones"}), 400

        az = session.get('allowed_zones')
        updated = []
        for upd in updates:
            zn = upd.get('zone_name')
            st = (upd.get('state') or '').strip().lower()
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

# ---------------- Banner ----------------
# GET (público): SiteBanner lo usa para leer el contenido
@admin_bp.route('/banner', methods=['GET'])
def public_get_banner():
    cfg = _load_banner_cfg()
    return jsonify(cfg), 200

# POST (solo admin): guardar configuración del banner
@admin_bp.route('/banner', methods=['POST'])
@require_admin_auth
def set_banner():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "Solo admin puede modificar el banner"}), 403
    data = request.get_json(silent=True) or {}
    new_cfg = {
        "enabled": bool(data.get('enabled', False)),
        "text": str(data.get('text') or ''),
        "variant": str(data.get('variant') or 'info').lower(),
        "link_text": str(data.get('link_text') or ''),
        "link_href": str(data.get('link_href') or ''),
        "id": str(data.get('id') or '')
    }
    saved = _save_banner_cfg(new_cfg)
    return jsonify({"success": True, "banner": saved}), 200
