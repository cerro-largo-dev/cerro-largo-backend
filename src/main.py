# main.py
import os
import sys
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# --- Import paths (raíz del proyecto) ---
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- DB & Blueprints ---
from src.models import db
from src.models.zone_state import ZoneState
from src.routes.user import user_bp
from src.routes.admin import admin_bp
from src.routes.report import report_bp
from src.routes.reportes import reportes_bp
from src.routes.notify import notify_bp      # Suscripciones WhatsApp
from src.routes.inumet import inumet_bp      # Alertas de Inumet

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FRONTEND_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN",
    "https://cerro-largo-frontend.onrender.com"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "app.db")

# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------
app = Flask(__name__)  # (no cambio el static_folder)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
)

# Base de datos (SQLite)
os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# CORS solo para /api/*
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": [FRONTEND_ORIGIN]}}
)

# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------
app.register_blueprint(user_bp,     url_prefix="/api")
app.register_blueprint(admin_bp,    url_prefix="/api/admin")
app.register_blueprint(report_bp,   url_prefix="/api/report")
app.register_blueprint(reportes_bp, url_prefix="/api")
app.register_blueprint(notify_bp,   url_prefix="/api/notify")
app.register_blueprint(inumet_bp,   url_prefix="/api/inumet")

# ---------------------------------------------------------------------------
# Seed inicial de zonas (sin cambios de lógica)
# ---------------------------------------------------------------------------
DESIRED_ZONE_ORDER = [
    "ACEGUÁ", "FRAILE MUERTO", "RÍO BRANCO", "TUPAMBAÉ", "LAS CAÑAS",
    "ISIDORO NOBLÍA", "CERRO DE LAS CUENTAS", "ARÉVALO", "BAÑADO DE MEDINA",
    "TRES ISLAS", "LAGUNA MERÍN", "CENTURIÓN", "RAMÓN TRIGO", "ARBOLITO",
    "QUEBRACHO", "PLÁCIDO ROSAS", "Melo (GBA)", "Melo (GBB)",
    "Melo (GBC)", "Melo (GCB)", "Melo (GEB)"
]

with app.app_context():
    db.create_all()
    try:
        if ZoneState.query.count() == 0:
            for name in DESIRED_ZONE_ORDER:
                exists = ZoneState.query.filter(ZoneState.name == name).first()
                if not exists:
                    z = ZoneState(name=name, state="red", updated_at=datetime.utcnow())
                    db.session.add(z)
            db.session.commit()
    except Exception as e:
        print("Seed de zonas falló:", e)

# ---------------------------------------------------------------------------
# Rutas utilitarias
# ---------------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return jsonify({"ok": True}), 200

@app.route("/__ping")
def __ping():
    return jsonify({"ok": True, "app": "backend"}), 200

# ---------------------------------------------------------------------------
# Catch-all para SPA: NUNCA servir HTML para /api/*
# ---------------------------------------------------------------------------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    # Si la ruta apunta a API pero no existe, devolver JSON 404 (no HTML)
    if path.startswith("api/"):
        return jsonify({"ok": False, "error": "not found", "path": f"/{path}"}), 404

    # Si tenés carpeta estática configurada y existe archivo, permitir servirlo
    static_folder_path = app.static_folder and os.path.abspath(app.static_folder)
    if static_folder_path and os.path.isdir(static_folder_path):
        candidate = os.path.join(static_folder_path, path) if path else None
        if path and candidate and os.path.exists(candidate) and os.path.isfile(candidate):
            return send_from_directory(static_folder_path, path)
        index_path = os.path.join(static_folder_path, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, "index.html")

    # Respuesta por defecto si no hay estáticos
    return jsonify({"message": "Backend activo"}), 200

# ---------------------------------------------------------------------------
# Manejo de errores: devolver JSON SOLO para /api/*
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def _not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "not found", "path": request.path}), 404
    # fuera de /api mantiene el comportamiento (HTML) del catch-all/Flask
    return e, 404

@app.errorhandler(405)
def _method_not_allowed(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "method not allowed", "path": request.path}), 405
    return e, 405

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
