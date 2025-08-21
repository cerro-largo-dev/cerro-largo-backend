# src/routes/banner.py
from flask import Blueprint, jsonify, request
from src.models.banner import db, BannerConfig

banner_bp = Blueprint("banner", __name__)

@banner_bp.route("/banner", methods=["GET"])
def get_public_banner():
    b = db.session.get(BannerConfig, 1)
    if not b:
        b = BannerConfig(id=1, enabled=False, text="", variant="info")
        db.session.add(b)
        db.session.commit()
    return jsonify(b.to_dict()), 200

@banner_bp.route("/admin/banner", methods=["GET", "PUT", "PATCH"])
def admin_banner():
    # ⚠️ Si tienes auth de admin, ponla aquí
    b = db.session.get(BannerConfig, 1)
    if not b:
        b = BannerConfig(id=1, enabled=False, text="", variant="info")
        db.session.add(b)
        db.session.commit()

    if request.method == "GET":
        return jsonify(b.to_dict()), 200

    data = request.get_json(silent=True) or {}
    if "enabled" in data: b.enabled = bool(data["enabled"])
    if "text" in data: b.text = str(data["text"] or "")
    if "variant" in data: b.variant = str(data["variant"] or "info").lower()
    if "link_text" in data: b.link_text = str(data["link_text"] or "")
    if "link_href" in data: b.link_href = str(data["link_href"] or "")

    db.session.commit()
    return jsonify(b.to_dict()), 200
