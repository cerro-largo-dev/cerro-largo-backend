# src/main.py
import os
from datetime import timedelta
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash

# Imports del proyecto (ajustá si cambian)
from models import db
from models.user import User
from routes.user import user_bp
from routes.admin import admin_bp
from routes.report import report_bp
from routes.reportes import reportes_bp


def create_app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")  # aquí está tu index.html y /assets

    # static_url_path="" => sirve /assets/* directamente en raíz
    app = Flask(__name__, static_folder=static_dir, static_url_path="")

    # ===== Config =====
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24))
    default_sqlite_path = os.path.join(base_dir, "database", "app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", f"sqlite:///{default_sqlite_path}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Sesión
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False") == "True"

    # CORS solo para pruebas locales (no necesario para el panel en el mismo dominio)
    CORS(app, supports_credentials=True, origins=["http://localhost:5173", "http://localhost:3000"])

    # ===== DB & admin bootstrap =====
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
                db.session.add(User(username="admin", password_hash=hashed, role="admin"))
                db.session.commit()
                app.logger.info("Usuario 'admin' creado desde variables de entorno.")

    # ===== Blueprints API =====
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(report_bp, url_prefix="/api/report")
    app.register_blueprint(reportes_bp, url_prefix="/api/reportes")

    # ===== Health =====
    @app.get("/api/health")
    def health():
        return jsonify(ok=True, service="backend")

    # ===== Raíz: servir tu panel (index.html) =====
    @app.get("/")
    def root():
        # Sirve src/static/index.html
        return app.send_static_file("index.html")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
