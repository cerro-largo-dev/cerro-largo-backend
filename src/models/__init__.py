# src/models/__init__.py
from flask_sqlalchemy import SQLAlchemy

# ÚNICA instancia global de SQLAlchemy para toda la app
db = SQLAlchemy()

# Importá los modelos aquí (después de definir db) para registrarlos
# OJO: todos los modelos deben importar "db" desde este módulo.
from .banner import BannerConfig  # noqa: E402,F401
# Si tenés más modelos: from .reporte import Reporte, FotoReporte, ...


from .reporte import Reporte, FotoReporte


