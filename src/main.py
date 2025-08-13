import os
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash

# Imports de tu proyecto (ajusta si tus módulos tienen otros nombres)
from models import db
from routes.user import user_bp
from routes.admin import admin_bp
from routes.report import report_bp
from routes.reportes import reportes_bp
from models.user import User


def create_app():
    app = Flask(__name__)

    # ---- Configuración por variables de entorno (Render las inyecta) ----
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24))

    # Ruta por defecto: sqlite en src/database/app.db (absoluta, robusta para Render)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_sqlite_path = os.path.join(base_dir, "database", "app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{default_sqlite_path}",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---- CORS: tu frontend en Render + localhost para desarrollo ----
    FRONTEND_ORIGINS = [
        "https://cerro-largo-frontend.onrender.com",
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    CORS(app, supports_credentials=True, origins=FRONTEND_ORIGINS)

    # ---- Inicializar DB y bootstrap de admin (solo si ADMIN_PASSWORD existe) ----
    db.init_app(app)
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            app.logger.error(f"[DB] create_all error: {e}")

        admin_pass = os.getenv("ADMIN_PASSWORD")
        if admin_pass:
            admin = User.query.filter_by(username="admin").first()
            if not admin:
                hashed = generate_password_hash(admin_pass, method="pbkdf2:sha256")
                admin = User(username="admin", password_hash=hashed, role="admin")
                db.session.add(admin)
                db.session.commit()
                app.logger.info("Usuario 'admin' creado desde variables de entorno.")
            else:
                app.logger.info("Usuario 'admin' ya existe; no se modifica.")

    # ---- Blueprints ----
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(report_bp, url_prefix="/api/report")
    app.register_blueprint(reportes_bp, url_prefix="/api/reportes")  # evita choques con /api

    # ---- Healthcheck simple ----
    @app.get("/api/health")
    def health():
        return jsonify(ok=True, service="backend", env=os.getenv("FLASK_ENV", "production"))

    return app


app = create_app()

if __name__ == "__main__":
    # Para desarrollo local; en Render usa gunicorn
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
.0", port=port, debug=debug_mode)
