# app.py
import os
from flask import Flask, jsonify
from flask_cors import CORS

# ---- IMPORTS de tu proyecto (ajusta si cambia la estructura) ----
# Asumo la estructura que venías usando:
# src/models/__init__.py define 'db'
# src/routes/user.py define user_bp, etc.
from src.models import db
from src.routes.user import user_bp
from src.routes.admin import admin_bp
from src.routes.report import report_bp
from src.routes.reportes import reportes_bp
from src.models.user import User  # Ajusta si el modelo admin está en otro módulo

from werkzeug.security import generate_password_hash


def create_app():
    app = Flask(
        __name__,
        static_folder=None,  # API pura; el frontend vive en Render (otro servicio)
    )

    # ---------- Configuración por variables de entorno ----------
    # Clave secreta
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24))

    # Base de datos
    # Ejemplos:
    #  - SQLite local: sqlite:///../database/app.db
    #  - Postgres Render: postgresql+psycopg2://user:pass@host:port/dbname
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "sqlite:///../database/app.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---------- CORS (frontend en Render + localhost dev) ----------
    FRONTEND_ORIGINS = [
        "https://cerro-largo-frontend.onrender.com",
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    CORS(app, supports_credentials=True, origins=FRONTEND_ORIGINS)

    # ---------- Inicializar DB ----------
    db.init_app(app)

    with app.app_context():
        # Crear tablas si no existen (útil en desarrollo)
        try:
            db.create_all()
        except Exception as e:
            app.logger.error(f"DB create_all error: {e}")

        # Semilla de usuario admin SI y solo SI hay contraseña en entorno
        admin_pass = os.getenv("ADMIN_PASSWORD")
        if admin_pass:
            admin = User.query.filter_by(username="admin").first()
            if not admin:
                hashed = generate_password_hash(admin_pass, method="pbkdf2:sha256")
                admin = User(username="admin", password_hash=hashed, role="admin")
                db.session.add(admin)
                db.session.commit()
                app.logger.info("Usuario admin creado por variables de entorno.")
            else:
                app.logger.info("Usuario admin ya existe; no se crea nuevamente.")

    # ---------- Blueprints ----------
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(report_bp, url_prefix="/api/report")
    app.register_blueprint(reportes_bp, url_prefix="/api")  # si tienes endpoints /api/reportes/*, ideal prefijar "/api/reportes"

    # ---------- Rutas básicas ----------
    @app.get("/api/health")
    def health():
        return jsonify(ok=True, service="backend", env=os.getenv("FLASK_ENV", "unknown"))

    return app


app = create_app()

if __name__ == "__main__":
    # En producción usa gunicorn/uvicorn; esto es solo para desarrollo local.
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
