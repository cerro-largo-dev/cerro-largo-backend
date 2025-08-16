import os
import sys
from datetime import datetime
from flask import Flask, jsonify, send_from_directory
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
from src.routes.notify import notify_bp  # ← NUEVO (suscripciones WhatsApp - stub)

# -----------------------------------------------------------------------------
# Config básica
# -----------------------------------------------------------------------------
FRONTEND_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN",
    "https://cerro-largo-frontend.onrender.com"
)

SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "app.db")

# -----------------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------------
app = Flask(__name__, static_folder="../static")

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

# CORS sólo para /api/* con credenciales
CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": [FRONTEND_ORIGIN]}}
)

# -----------------------------------------------------------------------------
# Blueprints
# -----------------------------------------------------------------------------
# Nota: mantenemos los prefijos que ya usás en prod
app.register_blueprint(user_bp,     url_prefix="/api/user")
app.register_blueprint(admin_bp,    url_prefix="/api/admin")
app.register_blueprint(report_bp,   url_prefix="/api/report")
app.register_blueprint(reportes_bp, url_prefix="/api/reportes")
app.register_blueprint(notify_bp,   url_prefix="/api/notify")  # ← NUEVO

# -----------------------------------------------------------------------------
# Seed inicial de zonas (sólo si la tabla está vacía)
# -----------------------------------------------------------------------------
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
                # Evita duplicar si ya existe por cualquier motivo
                exists = ZoneState.query.filter(ZoneState.name == name).first()
                if not exists:
                    z = ZoneState(name=name, state="red", updated_at=datetime.utcnow())
                    db.session.add(z)
            db.session.commit()
    except Exception as e:
        # No impedimos el arranque si el seed falla
        print("Seed de zonas falló:", e)

# -----------------------------------------------------------------------------
# Rutas utilitarias
# -----------------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return jsonify({"ok": True}), 200

# Servir estáticos si correspondiera (fallback SPA)
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """
    Si desplegás también archivos estáticos (no obligatorio en este backend),
    intenta servirlos. Si no, responde 404 o un mensajito claro.
    """
    static_folder_path = app.static_folder and os.path.abspath(app.static_folder)
    if static_folder_path and os.path.isdir(static_folder_path):
        # Intenta archivo directo
        candidate = os.path.join(static_folder_path, path)
        if path and os.path.exists(candidate) and os.path.isfile(candidate):
            return send_from_directory(static_folder_path, path)
        # Fallback a index.html (SPA)
        index_path = os.path.join(static_folder_path, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, "index.html")

    return jsonify({"message": "Backend API activo"}), 200

# -----------------------------------------------------------------------------
# Manejo global de errores
# -----------------------------------------------------------------------------
@app.errorhandler(Exception)
def handle_exception(e):
    # Evitá filtrar errores HTTP propios (si más adelante usás HTTPException)
    return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
