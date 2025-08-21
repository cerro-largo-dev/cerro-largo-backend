# src/routes/banner.py
from flask import Blueprint, jsonify, request
from src.models import db, BannerConfig
from datetime import datetime

banner_bp = Blueprint("banner", __name__)

# GET público
@banner_bp.route("/api/banner", methods=["GET"])
def get_banner():
    banner = BannerConfig.query.get(1)
    if not banner:
        return jsonify({
            "enabled": False,
            "id": "1",
            "text": "",
            "variant": "info",
            "link_text": "",
            "link_href": "",
            "updated_at": None
        })
    return jsonify(banner.to_dict())

# PUT / PATCH privado (admin)
@banner_bp.route("/api/admin/banner", methods=["PUT", "PATCH"])
def update_banner():
    data = request.get_json() or {}
    banner = BannerConfig.query.get(1)

    if not banner:
        banner = BannerConfig(id=1)

    # Validación: si lo habilitás, debe tener texto
    if data.get("enabled") and not str(data.get("text", "")).strip():
        return jsonify({"error": "El texto es requerido cuando enabled=true"}), 400

    # Solo actualizamos lo que venga en data
    if "enabled" in data:
        banner.enabled = bool(data["enabled"])
    if "text" in data:
        banner.text = data["text"]
    if "variant" in data:
        banner.variant = data["variant"]
    if "link_text" in data:
        banner.link_text = data["link_text"]
    if "link_href" in data:
        banner.link_href = data["link_href"]

    banner.updated_at = datetime.utcnow()

    db.session.add(banner)
    db.session.commit()
    return jsonify(banner.to_dict())
