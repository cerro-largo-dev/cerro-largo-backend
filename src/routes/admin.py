# src/routes/admin.py
from __future__ import annotations

import json
import os
import pathlib
import re
from functools import wraps
from typing import Any, Dict

from flask import Blueprint, jsonify, request, session

admin_bp = Blueprint("admin", __name__)

# -------------------------------------------------------------------
# Configuración
# -------------------------------------------------------------------

# 1) ADMIN_PASSWORD: no rompemos el arranque si falta, pero el login admin quedará deshabilitado
ADMIN_PASSWORD: str | None = os.environ.get("ADMIN_PASSWORD")  # <- ¡DEBES setearla en prod!

# 2) Banner: archivo donde se persiste la config pública del banner
BANNER_STORE_PATH: str = os.environ.get("BANNER_STORE_PATH", "storage/banner.json")

# 3) Sesión: flags/roles
SESSION_FLAG = "admin_authenticated"      # bool
SESSION_ROLE = "role"                     # 'admin' | 'editor'
SESSION_ALLOWED_ZONES = "allowed_zones"   # '*' | [..]

# 4) Validaciones de banner
_ALLOWED_VARIANTS = {"info", "warn", "alert", "success"}
_URL_RE = re.compile(r"^https?://", re.I)

_DEFAULT_BANNER: Dict[str, Any] = {
    "enabled": False,
    "text": "",
    "variant": "info",
    "link_text": "",
    "link_href": "",
    "id": "1",
}

# -------------------------------------------------------------------
# Helpers comunes
# -------------------------------------------------------------------

def _ensure_storage_dir():
    p = pathlib.Path(BANNER_STORE_PATH).parent
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)

def _load_banner_cfg() -> Dict[str, Any]:
    p = pathlib.Path(BANNER_STORE_PATH)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            cfg = {**_DEFAULT_BANNER, **(data or {})}
            cfg["enabled"] = bool(cfg.get("enabled", False))
            cfg["text"] = str(cfg.get("text") or "")
            cfg["variant"] = str(cfg.get("variant") or "info").lower()
            cfg["link_text"] = str(cfg.get("link_text") or "")
            cfg["link_href"] = str(cfg.get("link_href") or "")
            cfg["id"] = str(cfg.get("id") or "1")
            if cfg["variant"] not in _ALLOWED_VARIANTS:
                cfg["variant"] = "info"
            if cfg["link_href"] and not _URL_RE.match(cfg["link_href"]):
                # Sanitizar si quedó algo raro en disco
                cfg["link_href"] = ""
            return cfg
        except Exception:
            return dict(_DEFAULT_BANNER)
    return dict(_DEFAULT_BANNER)

def _save_banner_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_storage_dir()
    # Validación mínima antes de persistir
    cfg = {**_DEFAULT_BANNER, **(cfg or {})}
    cfg["enabled"] = bool(cfg.get("enabled", False))
    cfg["text"] = str(cfg.get("text") or "")
    variant = str(cfg.get("variant") or "info").lower()
    cfg["variant"] = variant if variant in _ALLOWED_VARIANTS else "info"
    cfg["link_text"] = str(cfg.get("link_text") or "")
    link = str(cfg.get("link_href") or "")
    if link and not _URL_RE.match(link):
        raise ValueError("link_href inválido (debe comenzar con http:// o https://)")
    cfg["link_href"] = link
    cfg["id"] = str(cfg.get("id") or "1")

    pathlib.Path(BANNER_STORE_PATH).write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return cfg

def _is_authenticated_admin() -> bool:
    return bool(session.get(SESSION_FLAG)) and session.get(SESSION_ROLE) == "admin"

def require_admin_auth(fn):
    """Protege endpoints solo-admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _is_authenticated_admin():
            return jsonify({"success": False, "message": "No autorizado"}), 401
        return fn(*args, **kwargs)
    return wrapper

# -------------------------------------------------------------------
# Auth del ADMIN (independiente del zone-editor que ya tienes resuelto)
# -------------------------------------------------------------------

@admin_bp.post("/admin/login")
def admin_login():
    """
    Login de administrador:
    - Espera JSON {"password": "..."}
    - Requiere que ADMIN_PASSWORD esté seteada en el entorno
    """
    data = request.get_json(silent=True) or {}
    pwd = str(data.get("password") or "")

    if not ADMIN_PASSWORD:
        # No crasheamos la app, pero avisamos claramente
        return (
            jsonify(
                {
                    "success": False,
                    "message": "ADMIN_PASSWORD no configurada en el entorno; login de administrador deshabilitado",
                }
            ),
            500,
        )

    if pwd and pwd == ADMIN_PASSWORD:
        # Seteamos sesión admin
        session[SESSION_FLAG] = True
        session[SESSION_ROLE] = "admin"
        session[SESSION_ALLOWED_ZONES] = "*"  # el admin ve/edita todo
        return jsonify({"success": True, "message": "Autenticación OK"}), 200

    return jsonify({"success": False, "message": "Contraseña incorrecta"}), 401


@admin_bp.post("/admin/logout")
def admin_logout():
    session.pop(SESSION_FLAG, None)
    session.pop(SESSION_ROLE, None)
    session.pop(SESSION_ALLOWED_ZONES, None)
    return jsonify({"success": True}), 200


@admin_bp.get("/admin/me")
def admin_me():
    """Estado de sesión (no revela mapeos de zonas)."""
    is_admin = _is_authenticated_admin()
    role = session.get(SESSION_ROLE) if is_admin else None
    return jsonify({"authenticated": is_admin, "role": role}), 200

# -------------------------------------------------------------------
# Banner público (GET) y edición (POST) solo-admin
# -------------------------------------------------------------------

@admin_bp.get("/banner")
def public_get_banner():
    """
    Público: devuelve la configuración de banner para el frontend.
    Si registras este blueprint con url_prefix='/api', la ruta pública será: GET /api/banner
    """
    return jsonify(_load_banner_cfg()), 200


@admin_bp.post("/admin/banner")
@require_admin_auth
def set_banner():
    """
    Solo admin: actualiza el banner.
    Body JSON esperado (todos opcionales):
    {
      "enabled": bool,
      "text": str,
      "variant": "info"|"warn"|"alert"|"success",
      "link_text": str,
      "link_href": "https://...",
      "id": str
    }
    """
    data = request.get_json(silent=True) or {}
    try:
        saved = _save_banner_cfg(data)
        return jsonify({"success": True, "banner": saved}), 200
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception:
        return jsonify({"success": False, "message": "Error guardando banner"}), 500
