# main.py (PostgreSQL por ENV → fallback a SQLite, con STATIC_ROOT) — actualizado
import os
import sys
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- Rutas de import (raíz del proyecto) ---
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- DB & Blueprints ---
from src.models import db
from src.models.zone_state import ZoneState
from src.routes.user import user_bp
from src.routes.admin import admin_bp
from src.routes.report import report_bp
from src.routes.reportes import reportes_bp
from src.routes.notify import notify_bp
from src.routes.inumet import inumet_bp
from src.routes.banner import banner_bp

# -----------------------------------------------------------------------------
# Config básica
# -----------------------------------------------------------------------------
FRONTEND_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN",
    "https://cerro-largo-frontend.onrender.com"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # validado abajo en prod

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "app.db")

# STATIC_ROOT real para subir/leer adjuntos (fotos de reportes)
STATIC_ROOT = os.environ.get("STATIC_ROOT", os.path.join(BASE_DIR, "static"))
os.makedirs(os.path.join(STATIC_ROOT, "uploads", "reportes"), exist_ok=True)

# -----------------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------------
# IMPORTANTE: Ya NO usamos static_folder=None para que current_app.static_folder exista
app = Flask(__name__, static_folder=STATIC_ROOT)
app.url_map.strict_slashes = False
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # 8 MB uploads
    JSON_SORT_KEYS=False,
)

# Respeta IP/Proto detrás de proxy (Render/NGINX)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# CORS sólo para /api/*
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": [FRONTEND_ORIGIN]}}
)

# Headers de seguridad básicos
@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=()")
    return resp

# Rate limiting (por IP)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"])

# -----------------------------------------------------------------------------
# Base de datos (usa DATABASE_URL si existe; si no, SQLite local)
# -----------------------------------------------------------------------------
os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
# Render a veces entrega postgres:// (SQLAlchemy requiere postgresql+psycopg2://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# En producción: exigir SECRET_KEY fuerte y ADMIN_PASSWORD definido/no por defecto
if os.getenv("FLASK_ENV") == "production":
    if SECRET_KEY == "change-this-secret":
        raise ValueError("SECRET_KEY environment variable is required in production")
    if (ADMIN_PASSWORD is None) or (ADMIN_PASSWORD.strip() == "") or (ADMIN_PASSWORD == "cerrolargo2025"):
        raise ValueError("ADMIN_PASSWORD environment variable is required for security in production")

# -----------------------------------------------------------------------------
# Blueprints
# -----------------------------------------------------------------------------
app.register_blueprint(user_bp,     url_prefix="/api")
app.register_blueprint(admin_bp,    url_prefix="/api/admin")
app.register_blueprint(report_bp,   url_prefix="/api/report")
app.register_blueprint(reportes_bp, url_prefix="/api")
app.register_blueprint(notify_bp,   url_prefix="/api/notify")
app.register_blueprint(inumet_bp,   url_prefix="/api/inumet")
app.register_blueprint(banner_bp,   url_prefix="/api")

# -----------------------------------------------------------------------------
# Seed inicial de zonas (si la tabla está vacía)
# -----------------------------------------------------------------------------
DESIRED_ZONE_ORDER = [
    'ACEGUÁ', 'ARBOLITO', 'ARÉVALO', 'BAÑADO DE MEDINA', 'CENTURIÓN',
    'CERRO DE LAS CUENTAS', 'FRAILE MUERTO', 'ISIDORO NOBLÍA', 'LAGUNA MERÍN',
    'LAS CAÑAS', 'PLÁCIDO ROSAS', 'QUEBRACHO', 'RAMÓN TRIGO', 'RÍO BRANCO',
    'TRES ISLAS', 'TUPAMBAÉ', 'Melo (GBA)', 'Melo (GBB)', 'Melo (GBC)',
    'Melo (GCB)', 'Melo (GEB)'
]
with app.app_context():
    db.create_all()
    try:
        if ZoneState.query.count() == 0:
            for name in DESIRED_ZONE_ORDER:
                # Compatibilidad: algunos modelos usan 'name' y otros 'zone_name'
                field = "name" if hasattr(ZoneState, "name") else "zone_name"
                exists = ZoneState.query.filter(
                    getattr(ZoneState, field) == name
                ).first()
                if not exists:
                    z = ZoneState(**{field: name}, state="red", updated_at=datetime.utcnow())
                    db.session.add(z)
            db.session.commit()
    except Exception as e:
        print("Seed de zonas falló:", e)

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/api/health")
@limiter.exempt
def api_health():
    return jsonify({"ok": True, "service": "backend"}), 200

@app.get("/api/healthz")
@limiter.exempt
def api_healthz():
    return jsonify({"ok": True, "service": "backend"}), 200

# -----------------------------------------------------------------------------
# Raíz y catch-all
# -----------------------------------------------------------------------------
@app.get("/")
@limiter.exempt
def root():
    return jsonify({"message": "Backend API activo"}), 200

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    if path.startswith("api/"):
        return jsonify({"ok": False, "error": "not found", "path": f"/{path}"}), 404
    return jsonify({"message": "Backend API activo"}), 200

# -----------------------------------------------------------------------------
# Errores como JSON en /api/*
# -----------------------------------------------------------------------------
@app.errorhandler(404)
def _not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "not found", "path": request.path}), 404
    return e, 404

@app.errorhandler(405)
def _method_not_allowed(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "method not allowed", "path": request.path}), 405
    return e, 405

@app.errorhandler(Exception)
def handle_exception(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": False, "error": "internal error"}), 500

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
