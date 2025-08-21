# scripts/init_banner.py
import os
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"].replace("postgres://","postgresql+psycopg2://",1)
engine = create_engine(url, pool_pre_ping=True, future=True)
sql = """
CREATE TABLE IF NOT EXISTS banner_config(
  id int PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  text varchar(500) NOT NULL DEFAULT '',
  variant varchar(20) NOT NULL DEFAULT 'info',
  link_text varchar(120),
  link_href varchar(500),
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO banner_config(id, enabled, text, variant)
  VALUES (1, false, '', 'info')
  ON CONFLICT (id) DO NOTHING;
"""
with engine.begin() as conn:
    conn.execute(text(sql))
print("OK banner_config")
