import os
import sys
from datetime import datetime
from flask import Flask, jsonify
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
from src.routes.notify import notify_bp  # Suscripciones WhatsApp

# ---------------------------------------------------------------------------
# Config básica
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
app = Flask(__name__)
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

# ---------------------------------------------------------------------------
# Seed inicial de zonas
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

# ---------------------------------------------------------------------------
# Manejo global de errores
# ---------------------------------------------------------------------------
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
