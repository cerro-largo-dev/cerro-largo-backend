# src/routes/admin.py
from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState, db
from functools import wraps
import os
import json
import unicodedata
import pathlib
import re

admin_bp = Blueprint("admin", __name__)

# ---------------- Config (ENV) ----------------
# Requiere que esté definida en el entorno. No hay fallback inseguro.
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

# Nombre de la cookie/flag de sesión
SESSION_FLAG = os.environ.get("SESSION_FLAG", "admin_authenticated")

# JSON con editores por zona (lo manejas en tu entorno): {"AREVALO":"<secreto>","MELO":"<secreto>"}
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

# Variantes permitidas y validador de URL
ALLOWED_BANNER_VARIANTS = {"info", "warn", "alert", "success"}
_URL_RE = re.compile(r"^https?://", re.I)

# ---------------- Utils ----------------
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def canon(s: str) -> str:
    if not s:
        return ""
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

ZONE_EDITORS = load_zone_editors()  # {"AREVALO":"<secreto>", ...}

# ---------------- Banner helpers ----------------
def _load_banner_cfg():
    try:
        p = pathlib.Path(BANNER_STORE_PATH)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            cfg = { **_DEFAULT_BANNER, **(data or {}) }
            # saneo/normalización
            cfg["enabled"]   = bool(cfg.get("enabled", False))
            cfg["text"]      = str(cfg.get("text", ""))
            v                = str(cfg.get("variant", "info")).lower().strip()
            cfg["variant"]   = v if v in ALLOWED_BANNER_VARIANTS else "info"
            cfg["link_text"] = str(cfg.get("link_text", ""))
            href             = str(cfg.get("link_href", ""))
            cfg["link_href"] = href if (not href or _URL_RE.match(href)) else ""
            cfg["id"]        = str(cfg.get("id", ""))
            # si no hay texto, deshabilitar
            if not cfg["text"].strip():
                cfg["enabled"] = False
            return cfg
    except Exception:
        pass
    return dict(_DEFAULT_BANNER)

def _save_banner_cfg(cfg: dict):
    clean = { **_DEFAULT_BANNER, **(cfg or {}) }
    # validar aquí también
    clean["enabled"] = bool(clean.get("enabled", False))
    clean["text"] = str(clean.get("text", ""))
    v = str(clean.get("variant", "info")).lower().strip()
    clean["variant"] = v if v in ALLOWED_BANNER_VARIANTS else "info"
    clean["link_text"] = str(clean.get("link_text", ""))
    href = str(clean.get("link_href", ""))
    clean["link_href"] = href if (not href or _URL_RE.match(href)) else ""
    clean["id"] = str(clean.get("id", ""))

    if not clean["text"].strip():
        clean["enabled"] = False

    p = pathlib.Path(BANNER_STORE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clean, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
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
@admin_bp.route("/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    pwd = str(data.get("password") or "")

    # 1) Admin total
    if pwd == ADMIN_PASSWORD:
        session[SESSION_FLAG] = True
        session["role"] = "admin"
        session["allowed_zones"] = "*"
        return jsonify({"success": True, "message": "Autenticación admin"}), 200

    # 2) Editor por zona (si coincide secreto de zona)
    zones = [z for z, passw in ZONE_EDITORS.items() if passw == pwd]
    if zones:
        session[SESSION_FLAG] = True
        session["role"] = "editor"
        session["allowed_zones"] = zones  # canónicas
        return jsonify({"success": True, "message": "Autenticación editor", "allowed_zones": zones}), 200

    return jsonify({"success": False, "message": "Contraseña incorrecta"}), 401

@admin_bp.route("/logout", methods=["POST"])
def admin_logout():
    session.pop(SESSION_FLAG, None)
    session.pop("role", None)
    session.pop("allowed_zones", None)
    return jsonify({"success": True, "message": "Sesión cerrada"}), 200

@admin_bp.route("/check-auth", methods=["GET"])
def check_auth():
    authed = session.get(SESSION_FLAG, False)
    role = session.get("role", "admin" if authed else None)
    az = session.get("allowed_zones", "*" if role == "admin" else [])
    return jsonify({"success": True, "authenticated": bool(authed), "role": role, "allowed_zones": az}), 200

# ---------------- Zonas ----------------
@admin_bp.route("/zones/states", methods=["GET"])
def get_zone_states():
    """Público (si querés, podés protegerlo agregando @require_admin_auth)."""
    try:
        states = ZoneState.get_all_states()  # { name: { state, ... }, ... }
        print(f"Estados obtenidos: {states}") # Added print statement
        return jsonify({"success": True, "states": states}), 200
    except Exception as e:
        print(f"Error en get_zone_states: {e}") # Added print statement
        return jsonify({"success": False, "message": f"Error al obtener estados: {str(e)}"}), 500

@admin_bp.route("/zones/update-state", methods=["POST"])
@require_admin_auth
def update_zone_state():
    try:
        data = request.get_json(silent=True) or {}
        zone_name = data.get("zone_name")
        state = (data.get("state") or "").strip().lower()
        if not zone_name or state not in ["green", "yellow", "red"]:
            return jsonify({"success": False, "message": "Datos inválidos"}), 400

        # Autorización por zona si es editor
        az = session.get("allowed_zones")
        if az != "*" and az is not None:
            if canon(zone_name) not in [canon(z) for z in (az or [])]:
                return jsonify({"success": False, "message": "No autorizado para esta zona"}), 403

        updated_zone = ZoneState.update_zone_state(zone_name, state, session.get("role", "admin"))
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

@admin_bp.route("/zones/bulk-update", methods=["POST"])
@require_admin_auth
def bulk_update_zones():
    try:
        data = request.get_json(silent=True) or {}
        updates = data.get("updates", [])
        if not isinstance(updates, list) or not updates:
            return jsonify({"success": False, "message": "No se proporcionaron actualizaciones"}), 400

        az = session.get("allowed_zones")
        updated = []
        for upd in updates:
            zn = upd.get("zone_name")
            st = (upd.get("state") or "").strip().lower()
            if not zn or st not in ["green", "yellow", "red"]:
                continue
            if az != "*" and az is not None and canon(zn) not in [canon(z) for z in (az or [])]:
                continue  # skip zonas no permitidas
            z = ZoneState.update_zone_state(zn, st, session.get("role", "editor"))
            if z:
                updated.append(z.to_dict())

        return jsonify({"success": True, "message": f"Se actualizaron {len(updated)} zonas", "updated_zones": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Error en actualización masiva: {str(e)}"}), 500

# ---------------- Banner ----------------
# GET (público): SiteBanner lo usa para leer el contenido
@admin_bp.route("/banner", methods=["GET"])
def public_get_banner():
    cfg = _load_banner_cfg()
    return jsonify(cfg), 200

# POST (solo admin): guardar configuración del banner
@admin_bp.route("/banner", methods=["POST"])
@require_admin_auth
def set_banner():
    if session.get("role") != "admin":
        return jsonify({"success": False, "message": "Solo admin puede modificar el banner"}), 403
    data = request.get_json(silent=True) or {}

    variant = str(data.get("variant") or "info").lower().strip()
    if variant not in ALLOWED_BANNER_VARIANTS:
        variant = "info"

    link_href = str(data.get("link_href") or "")
    if link_href and not _URL_RE.match(link_href):
        return jsonify({"success": False, "message": "link_href inválido (requiere http/https)"}), 400

    new_cfg = {
        "enabled": bool(data.get("enabled", False)),
        "text": str(data.get("text") or ""),
        "variant": variant,
        "link_text": str(data.get("link_text") or ""),
        "link_href": link_href,
        "id": str(data.get("id") or "")
    }
    saved = _save_banner_cfg(new_cfg)
    return jsonify({"success": True, "banner": saved}), 200


