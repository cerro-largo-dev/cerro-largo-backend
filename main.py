import os
import sys

# Mantener el sys.path para importar desde la raíz del proyecto (como tenías)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # importa la factoría definida en app.py

# Instancia WSGI para producción (Render/Gunicorn usa "app")
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
