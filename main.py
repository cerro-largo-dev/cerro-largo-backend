import os
import sys
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

# Ajustar el sys.path para que la importación de módulos desde la raíz del proyecto sea correcta.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Importar la instancia global de base de datos y el modelo ZoneState.
from src.models import db
from src.models.zone_state import ZoneState
from src.routes.user import user_bp
from src.routes.admin import admin_bp
from src.routes.report import report_bp
from src.routes.reportes import reportes_bp

# Crear la aplicación Flask y configurar la carpeta estática donde se servirán los archivos del front-end.
app = Flask(__name__, static_folder="../static")

# 🔐 Clave de sesión y flags para cookies cross-site (Safari/iOS exige esto)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cerro_largo_secret_key_2025")
app.config["SESSION_COOKIE_SAMESITE"] = "None"   # ← importante para cross-site
app.config["SESSION_COOKIE_SECURE"] = True       # ← requiere HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True

# 🌐 CORS con credenciales SOLO para tu(s) frontend(s)
# Puedes definir varios orígenes separados por coma en FRONTEND_ORIGIN
origins_env = os.environ.get("FRONTEND_ORIGIN", "https://cerro-largo-frontend.onrender.com")
origins = [o.strip() for o in origins_env.split(",") if o.strip()]
CORS(
    app,
    resources={r"/api/*": {"origins": origins}},
    supports_credentials=True,
)

# Registrar los blueprints de la API (igual que tenías)
app.register_blueprint(user_bp, url_prefix="/api")
app.register_blueprint(admin_bp, url_prefix="/api/admin")
app.register_blueprint(report_bp, url_prefix="/api/report")
app.register_blueprint(reportes_bp, url_prefix="/api")

# Configuración de la base de datos (SQLite en carpeta superior /database)
base_dir = os.path.dirname(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(base_dir, 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Asegurar directorio DB
os.makedirs(os.path.join(base_dir, 'database'), exist_ok=True)

# Crear tablas e inicializar si está vacío
with app.app_context():
    db.create_all()
    if ZoneState.query.count() == 0:
        municipios_default = [
            'ACEGUÁ', 'ARBOLITO', 'BAÑADO DE MEDINA', 'CERRO DE LAS CUENTAS',
            'FRAILE MUERTO', 'ISIDORO NOBLÍA', 'LAGO MERÍN', 'LAS CAÑAS',
            'MELO', 'PLÁCIDO ROSAS', 'RÍO BRANCO', 'TOLEDO', 'TUPAMBAÉ',
            'ARÉVALO', 'NOBLÍA', 'Melo (GBB)', 'Melo (GCB)'
        ]
        for municipio in municipios_default:
            ZoneState.update_zone_state(municipio, 'green', 'sistema')
        print(f"Inicializados {len(municipios_default)} municipios con estado 'green'")

# Salud
@app.route("/api/health")
def health_check():
    return jsonify({'status': 'healthy', 'service': 'cerro-largo-backend'}), 200

# Servir estáticos / index.html si procede
@app.route("/", defaults={'path': ''})
@app.route("/<path:path>")
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    file_path = os.path.join(static_folder_path, path)
    if path != "" and os.path.exists(file_path):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, "index.html")
        else:
            return "index.html not found", 404

# Manejo global de errores
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
