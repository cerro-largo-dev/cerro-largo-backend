"""
Inicializa la instancia de SQLAlchemy compartida por todos los modelos.

Esta instancia debe importarse desde otros módulos para evitar crear
múltiples instancias de SQLAlchemy y asegurar que esté asociada al
objeto Flask correctamente.  En `main.py` se llama a
`db.init_app(app)` una sola vez.
"""

from flask_sqlalchemy import SQLAlchemy

# Instancia global de SQLAlchemy para toda la aplicación
db = SQLAlchemy()
