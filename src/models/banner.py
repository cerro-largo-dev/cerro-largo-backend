# src/models/banner.py
from src.models import db
from datetime import datetime, timezone

def _iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

class BannerConfig(db.Model):
    __tablename__ = "banner_config"

    id = db.Column(db.Integer, primary_key=True, default=1)  # 1 sola fila (id=1)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    text = db.Column(db.String(500), nullable=False, default="")
    variant = db.Column(db.String(20), nullable=False, default="info")  # info|warn|alert|success
    link_text = db.Column(db.String(120), nullable=True)
    link_href = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "enabled": bool(self.enabled),
            "text": self.text or "",
            "variant": (self.variant or "info").lower(),
            "link_text": self.link_text or "",
            "link_href": self.link_href or "",
            "updated_at": _iso(self.updated_at),
        }
