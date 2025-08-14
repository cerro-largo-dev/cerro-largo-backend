# app.py (raíz del backend)
import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from src.models import db
from src.models.zone_state import ZoneState

def create_app():
    # Si querés servir un build estático, dejá static_folder="static"
    app = Flask(__name__, static_folder="static")

    # SECRET_KEY (desde env; con fallback para desarrollo)
    secret = os.environ.get("SECRET_KEY") or "cerro_largo_secret_key_2025"
    if "SECRET_KEY" not in os.environ:
        print("WARN: SECRET_KEY no seteada en entorno; usando valor de desarrollo.")
    app.config["SECRET_KEY"] = secret

    # DB en ./database/app.db (raíz del repo)
    db_path = os.path.join(os.path.dirname(__file__), "database", "app.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # CORS (habilita Authorization para JWT)
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": [
            "https://cerro-largo-frontend.onrender.com",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]}},
        allow_headers=["Authorization", "Content-Type"],
    )

    # ORM
    db.init_app(app)

    # Blueprints de tu API
    from src.routes.user import user_bp
    from src.routes.admin import admin_bp
    from src.routes.report import report_bp
    from src.routes.reportes import reportes_bp

    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(report_bp, url_prefix="/api/report")
    app.register_blueprint(reportes_bp, url_prefix="/api")

    # Healthcheck
    @app.get("/api/health")
    def health():
        return jsonify({"status": "healthy", "service": "cerro-largo-backend"}), 200

    # (Opcional) servir estáticos si subís el build del front a ./static
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve(path):
        if app.static_folder and path:
            fp = os.path.join(app.static_folder, path)
            if os.path.exists(fp):
                return send_from_directory(app.static_folder, path)
        idx = os.path.join(app.static_folder or "", "index.html")
        if idx and os.path.exists(idx):
            return send_from_directory(app.static_folder, "index.html")
        return "index.html not found", 404

    # ---- Seed en arranque (idempotente) ----
    with app.app_context():
        print("DB path en runtime:", db_path)
        db.create_all()

        # Municipios por defecto (solo si la tabla está vacía)
        if ZoneState.query.count() == 0:
            municipios = [
                "ACEGUÁ", "ARBOLITO", "BAÑADO DE MEDINA", "CERRO DE LAS CUENTAS",
                "FRAILE MUERTO", "ISIDORO NOBLÍA", "LAGO MERÍN", "LAS CAÑAS",
                "MELO", "PLÁCIDO ROSAS", "RÍO BRANCO", "TUPAMBAÉ",
                "ARÉVALO", "NOBLÍA", "Melo (GBB)", "Melo (GCB)"
            ]
            for m in municipios:
                ZoneState.update_zone_state(m, "green", "sistema")
            print(f"Inicializados {len(municipios)} municipios con estado 'green'")

        # ADMIN: crear o actualizar SIEMPRE (para que puedas loguearte)
        from src.models.user import User  # importar aquí para evitar ciclos

        admin_email = os.environ.get("ADMIN_EMAIL", "admin@cerrolargo.gub.uy")
        admin_pass  = os.environ.get("ADMIN_PASSWORD", "admin2025")

        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(
                email=admin_email,
                nombre="Administrador Principal",
                role="ADMIN",
                municipio_id=None,
                is_active=True,
                force_password_reset=False,
            )
            db.session.add(admin)
            print("Usuario ADMIN inicial creado.")
        else:
            admin.is_active = True
            admin.force_password_reset = False
            print("Usuario ADMIN encontrado; actualizando contraseña…")

        # Fuerza una contraseña conocida con Argon2 (según tu modelo User)
        admin.set_password(admin_pass)
        db.session.commit()
        print("Usuario ADMIN verificado/actualizado.")

    return app

# Export para gunicorn (si quisieras usar `gunicorn app:app`)
app = create_app()

# Ejecución local
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
