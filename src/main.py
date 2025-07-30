import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from src.models.user import db
from src.models.zone_state import ZoneState
from src.routes.user import user_bp
from src.routes.admin import admin_bp
from src.routes.report import report_bp

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'cerro_largo_secret_key_2025'

# Habilitar CORS para todas las rutas
CORS(app, supports_credentials=True, origins="*")

# Registrar blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(report_bp, url_prefix='/api/report')

# Configuración de base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Crear directorio de base de datos si no existe
os.makedirs(os.path.join(os.path.dirname(__file__), 'database'), exist_ok=True)

with app.app_context():
    db.create_all()
    
    # Inicializar datos por defecto si la base de datos está vacía
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

# Ruta de salud
@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'cerro-largo-backend'}), 200

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
