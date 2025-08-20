# init_db.py
import os
from flask import Flask
from src.models import db  # importa la instancia global de SQLAlchemy

def create_app():
    app = Flask(__name__)

    # --- Conexión a la base ---
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    DB_PATH = os.path.join(BASE_DIR, "database", "app.db")

    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    return app

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        print("✔ Tablas creadas/migradas en la base configurada.")
