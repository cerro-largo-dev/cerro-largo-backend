import os
import logging
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from src.models import db
from src.models.zone_state import ZoneState

logger = logging.getLogger(__name__)

def create_app():
    # Si querés además servir un build estático del front desde /static, dejá static_folder="static"
    app = Flask(__name__, static_folder="static")

    # 🔐 SECRET_KEY desde entorno (obligatorio)
    try:
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    except KeyError:
        raise RuntimeError("SECRET_KEY no seteada en el entorno (ej: SECRET_KEY=cerrolargo2025).")

    # 📦 Base de datos en RAÍZ: database/app.db
    db_path = os.path.join(os.path.dirname(__file__), "database", "app.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # 🌐 CORS (origins explícitos; evita '*'+credentials)
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": [
            "https://cerro-largo-frontend.onrender.com",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]}}
    )

    # ORM
    db.init_app(app)

    # Blueprints (todas tus “comunicaciones”/rutas viven acá)
    from src.routes.user import user_bp
    from src.routes.admin import admin_bp
    from src.routes.report import report_bp
    from src.routes.reportes import reportes_bp
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(report_bp, url_prefix="/api/report")
    app.register_blueprint(reportes_bp, url_prefix="/api")

    # Health
    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "healthy", "service": "cerro-largo-backend"}), 200

    # (Opcional) Servir estáticos si ponés el build del front en ./static
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve(path):
        if app.static_folder and path:
            file_path = os.path.join(app.static_folder, path)
            if os.path.exists(file_path):
                return send_from_directory(app.static_folder, path)
        index_path = os.path.join(app.static_folder or "", "index.html")
        if index_path and os.path.exists(index_path):
            return send_from_directory(app.static_folder, "index.html")
        return "index.html not found", 404

    # Seed / datos iniciales (idempotente)
    with app.app_context():
        print("DB path en runtime:", db_path)
        db.create_all()

        # Municipios por defecto
        if ZoneState.query.count() == 0:
            municipios_default = [
                "ACEGUÁ","ARBOLITO","BAÑADO DE MEDINA","CERRO DE LAS CUENTAS",
                "FRAILE MUERTO","ISIDORO NOBLÍA","LAGO MERÍN","LAS CAÑAS",
                "MELO","PLÁCIDO ROSAS","RÍO BRANCO","TUPAMBAÉ",
                "ARÉVALO","NOBLÍA","Melo (GBB)","Melo (GCB)"
            ]
            for m in municipios_default:
                ZoneState.update_zone_state(m, "green", "sistema")
            print(f"Inicializados {len(municipios_default)} municipios con estado 'green'")

        # Admin: crear o verificar/actualizar
        from src.models.user import User  # evitar ciclos
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
            admin.set_password(admin_pass)
            db.session.add(admin)
            db.session.commit()
            print("Usuario ADMIN inicial creado.")
        else:
            admin.is_active = True
            admin.force_password_reset = False
            admin.set_password(admin_pass)  # fuerza contraseña conocida al levantar
            db.session.commit()
            print("Usuario ADMIN verificado/actualizado.")

    return app

# (Opcional) correr local: python app.py
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
