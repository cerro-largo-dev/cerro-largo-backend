import os
import sys
# DON\'T CHANGE THIS !!!
# Ajustar el sys.path para que la importación de módulos desde la raíz del proyecto sea correcta.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

# Importar la instancia global de base de datos y el modelo ZoneState.
from src.models import db
from src.models.zone_state import ZoneState
from src.models.user import User
from werkzeug.security import generate_password_hash
from src.routes.user import user_bp
from src.routes.admin import admin_bp
from src.routes.report import report_bp
from src.routes.reportes import reportes_bp


# Crear la aplicación Flask y configurar la carpeta estática donde se servirán los archivos del front-end.
app = Flask(__name__, static_folder="../static")
app.config["SECRET_KEY"] = "cerro_largo_secret_key_2025"

# Habilitar CORS para todas las rutas (permitir credenciales y cualquier origen).
CORS(app, supports_credentials=True, origins="*")

# Registrar los blueprints de la API
app.register_blueprint(user_bp, url_prefix=\"/api\")
app.register_blueprint(admin_bp, url_prefix=\"/api/admin\")
app.register_blueprint(report_bp, url_prefix="/api/report")
app.register_blueprint(reportes_bp, url_prefix="/api/reportes")

# Configuración de la base de datos
# El fichero app.db se encuentra en el directorio de nivel superior \'database\' (fuera de src),
# por lo que calculamos la ruta subiendo un nivel desde __file__.
base_dir = os.path.dirname(os.path.dirname(__file__))
app.config[\"SQLALCHEMY_DATABASE_URI\"] = f"sqlite:///{os.path.join(base_dir, \'database\', \'app.db\')}"
app.config[\"SQLALCHEMY_TRACK_MODIFICATIONS\"] = False
db.init_app(app)

# Asegurarse de que el directorio de la base de datos exista
os.makedirs(os.path.join(base_dir, \'database\'), exist_ok=True)

# Crear tablas y valores iniciales si es necesario
with app.app_context():
    db.create_all()

    # Crear un usuario administrador por defecto si no existe
    if User.query.filter_by(username=\'admin\').first() is None:
        hashed_password = generate_password_hash(\'cerrolargo2025\', method=\'pbkdf2:sha256\')
        admin_user = User(username=\'admin\', password_hash=hashed_password, role=\'admin\', municipality=None)
        db.session.add(admin_user)
        db.session.commit()
        print(\'Usuario administrador por defecto creado.\')

    # Inicializar los estados predeterminados de los municipios si la tabla está vacía
    municipios_default = [
        \'ACEGUÁ\', \'ARBOLITO\', \'BAÑADO DE MEDINA\', \'CERRO DE LAS CUENTAS\',
        \'FRAILE MUERTO\', \'ISIDORO NOBLÍA\', \'LAGO MERÍN\', \'LAS CAÑAS\',
        \'MELO\', \'PLÁCIDO ROSAS\', \'RÍO BRANCO\', \'TOLEDO\', \'TUPAMBAÉ\',
        \'ARÉVALO\', \'NOBLÍA\', \'Melo (GBB)\' , \'Melo (GCB)\'
    ]

    if ZoneState.query.count() == 0:
        for municipio in municipios_default:
            ZoneState.update_zone_state(municipio, \'green\', \'sistema\')
        print(f\'Inicializados {len(municipios_default)} municipios con estado green\')

    # Crear usuarios alcalde por defecto si no existen
    for municipio in municipios_default:
        username_alcalde = f"alcalde{municipio.replace(' ', '').replace('(', '').replace(')', '').lower()}2025"
        password_alcalde = f"pass{municipio.replace(' ', '').replace('(', '').replace(')', '').lower()}"
        
        if User.query.filter_by(username=username_alcalde).first() is None:
            hashed_password_alcalde = generate_password_hash(password_alcalde, method=\'pbkdf2:sha256\')
            alcalde_user = User(username=username_alcalde, password_hash=hashed_password_alcalde, role=\'alcalde\', municipality=municipio)
            db.session.add(alcalde_user)
            db.session.commit()
            print(f\'Usuario alcalde {username_alcalde} creado para {municipio}.\')

# Ruta de salud para verificar que el servicio está activo
@app.route(\"/api/health\")
def health_check():
    return jsonify({\'status\': \'healthy\', \'service\': \'cerro-largo-backend\'}), 200


# Enrutamiento para servir archivos estáticos (React build) o index.html por defecto
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
