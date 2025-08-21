# src/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class BannerConfig(db.Model):
    __tablename__ = "banner_config"
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    text = db.Column(db.String, default="")
    variant = db.Column(db.String, default="info")  # info, warn, success, etc
    link_text = db.Column(db.String, default="")
    link_href = db.Column(db.String, default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "enabled": self.enabled,
            "text": self.text,
            "variant": self.variant,
            "link_text": self.link_text,
            "link_href": self.link_href,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
