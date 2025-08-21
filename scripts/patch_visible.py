import os
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"].replace("postgres://","postgresql+psycopg2://",1)
engine = create_engine(url, pool_pre_ping=True, future=True)
with engine.begin() as conn:
    conn.execute(text(
        "ALTER TABLE reportes ADD COLUMN IF NOT EXISTS visible boolean NOT NULL DEFAULT false;"
    ))
print("OK: columna visible creada/asegurada")
